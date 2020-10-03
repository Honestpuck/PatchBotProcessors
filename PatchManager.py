#!/usr/bin/env python3
#
# PatchManager v2.0.1
#
# Tony Williams 2020-03-10
# David Elkin-Bram 2020-09-24
#
# ARW 2020-06-22 Major code clean and refactor
# MVP-2 2020-09-24 Adjustments for recipe chaining and messaging

"""See docstring for PatchManager class"""

from os import path
import plistlib
import xml.etree.ElementTree as ET
import datetime
import logging.handlers
import requests

from autopkglib import Processor, ProcessorError

APPNAME = "PatchManager"
LOGLEVEL = logging.DEBUG

__all__ = [APPNAME]


class Package:
    """A package. This exists merely to carry the variables"""

    # the application part of the package name matching the test policy
    package = ""
    patch = ""  # name of the patch definition
    name = ""  # full name of the package '<package>-<version>.pkg'
    version = ""  # the version of our package
    idn = ""  # id of the package in our JP server
    test_weekdays = ""  # allowed weekdays for deployment to test
    test_not_before = ""  # earliest time for deployment to test
    test_not_after = ""  # latest time for deployment to test


class PatchManager(Processor):
    """Custom processor for autopkg that updates a patch policy
    and test policy for a package"""

    description = __doc__

    input_variables = {
        "package": {"required": True, "description": "Application part of package name"},
        "patch": {"required": False, "description": "Patch name"},
        "test_weekdays": {
            "required": False,
            "description": "Limit weekdays for deployment to test"},
        "test_not_before": {
            "required": False,
            "description": "Earliest time for deployment to test"},
        "test_not_after": {
            "required": False,
            "description": "Latest time for deployment to test"},

    }
    output_variables = {
        "patch_manager_summary_result": {"description": "Summary of action"}
    }

    pkg = Package()

    def setup_logging(self):
        """Defines a nicely formatted logger"""
        LOGFILE = "/usr/local/var/log/%s.log" % APPNAME

        self.logger = logging.getLogger(APPNAME)
        # we may be the second and subsequent iterations of JPCImporter
        # and already have a handler.
        if len(self.logger.handlers):
            return
        ch = logging.handlers.TimedRotatingFileHandler(
            LOGFILE, when="D", interval=1, backupCount=7
        )
        ch.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self.logger.addHandler(ch)
        self.logger.setLevel(LOGLEVEL)


    def autopkg_msg(self, the_msg):
        """Defines a simple prefixed string to stdout for autopkg"""
        print(APPNAME + ': ' + the_msg)


    ## essentially identical to Production.py/time_for_production(), w/o days delta
    def time_for_testing(self):
        """determine whether or not to move to testing"""
        self.logger.debug("Time For Testing?")

        # now date object
        today = datetime.datetime.now()
        self.logger.debug("Set now: " + str(today))

        # test weekday, if empty skip the weekday test
        if self.pkg.test_weekdays != "":
            # get weekday integer, 0 = Monday
            t_wd = datetime.datetime.weekday(today)
            self.logger.debug("Set weekday: " + str(t_wd))
            # is the weekday in the provided integers string?
            if str(t_wd) not in self.pkg.test_weekdays:
                self.autopkg_msg(
                    "Weekday %d not in allowed weekdays %s, skipping"
                    % (t_wd, self.pkg.test_weekdays)
                )
                return False

        # test start time, if empty skip the time test
        if self.pkg.test_not_before != "":
            # get start time as date object
            t_start = datetime.datetime.strptime(self.pkg.test_not_before,'%H:%M')
            # is now before this start time?
            if today.time() < t_start.time():
                self.autopkg_msg(
                    "Current time %s is before testing start time %s"
                    % (today.time(), t_start.time())
                )
                return False

        # test end time, if empty skip the time test
        if self.pkg.test_not_after != "":
            # get end time as date object
            t_end = datetime.datetime.strptime(self.pkg.test_not_after,'%H:%M')
            # is now after this start time?
            if today.time() > t_end.time():
                self.autopkg_msg(
                    "Current time %s is after testing end time %s"
                    % (today.time(), t_end.time())
                )
                return False

        # all good, move to testing
        self.logger.debug("Moving Now")
        self.autopkg_msg("Moving Now")
        return True



    def policy(self):
        """Download the TEST policy for the app and return version string"""
        self.logger.warning(
            "******** Starting policy %s *******" % self.pkg.package
        )
        # Which pref format to use, autopkg or jss_importer
        autopkg = False
        if autopkg:
            plist = path.expanduser(
                "~/Library/Preferences/com.github.autopkg.plist"
            )
            fp = open(plist, "rb")
            prefs = plistlib.load(fp)
            self.base = prefs["JSS_URL"] + "/JSSResource/"
            self.auth = (prefs["API_USERNAME"], prefs["API_PASSWORD"])
        else:
            plist = path.expanduser("~/Library/Preferences/JPCImporter.plist")
            fp = open(plist, "rb")
            prefs = plistlib.load(fp)
            self.base = prefs["url"] + "/JSSResource/"
            self.auth = (prefs["user"], prefs["password"])
        policy_name = "TEST-{}".format(self.pkg.package)
        self.autopkg_msg("Geting version from policy: %s" % policy_name)
        url = self.base + "policies/name/{}".format(policy_name)
        self.logger.debug(
            "About to make request URL %s, auth %s" % (url, self.auth)
        )
        ret = requests.get(url, auth=self.auth)
        if ret.status_code != 200:
            self.logger.debug(
                "TEST Policy %s not found error: %s"
                % (policy_name, ret.status_code)
            )
            self.logger.debug(
                "Policy get for: %s failed with code: %s"
                % (url, ret.status_code)
            )
            self.autopkg_msg("Policy not found, exiting")
            exit()
        self.logger.debug("TEST policy found")
        root = ET.fromstring(ret.text)
        self.pkg.idn = root.find(
            "package_configuration/packages/package/id"
        ).text
        self.pkg.name = root.find(
            "package_configuration/packages/package/name"
        ).text
        self.pkg.version = self.pkg.name.split("-", 1)[1][:-4]
        self.logger.debug(
            "Version in TEST Policy %s " % self.pkg.version
        )
        # return the version number
        self.autopkg_msg("Found version: %s" % self.pkg.version)
        return self.pkg.version

    def patch(self):
        """Now we check for, then update the patch definition"""
        self.autopkg_msg("Updating Patch Softare Title: %s" % self.pkg.patch)
        # download the list of titles
        url = self.base + "patchsoftwaretitles"
        self.logger.debug("About to request PST list %s", url)
        ret = requests.get(url, auth=self.auth)
        if ret.status_code != 200:
            raise ProcessorError(
                "Patch list download failed: {} : {}".format(
                    ret.status_code, url
                )
            )
        self.logger.debug("Got PST list")
        root = ET.fromstring(ret.text)
        # loop through 'patchsoftwaretitles' list to find our title
        ident = 0
        for ps_title in root.findall("patch_software_title"):
            if ps_title.findtext("name") == self.pkg.patch:
                ident = ps_title.findtext("id")
                self.logger.debug("PST ID found")
                break
        if ident == 0:
            raise ProcessorError(
                "Patch list did not contain title: {}".format(self.pkg.patch)
            )
        # get the patch list for our title
        url = self.base + "patchsoftwaretitles/id/" + str(ident)
        self.logger.debug("About to request PST by ID: %s" % url)
        ret = requests.get(url, auth=self.auth)
        if ret.status_code != 200:
            raise ProcessorError(
                "Patch software download failed: {} : {}".format(
                    str(ident), self.pkg.name
                )
            )
        self.logger.debug("Got our PST")
        root = ET.fromstring(ret.text)
        # find the patch version that matches our version
        done = False
        for record in root.findall("versions/version"):
            if self.pkg.version in record.findtext("software_version"):
                self.logger.debug("Found our version")
                if record.findtext("package/name"):
                    self.logger.debug("Definition already points to package")
                    return 0
                package = record.find("package")
                add = ET.SubElement(package, "id")
                add.text = self.pkg.idn
                add = ET.SubElement(package, "name")
                add.text = self.pkg.name
                done = True
                break
        if not done:
            # this isn't really an error but we want to know anyway
            # and we need to exit so raising an error is the easiest way to
            # do that feeding info to Teams
            # exit gracefully to allow chained processors to continue
            self.logger.debug(
                "Patch definition version not found: {} : {} : {}".format(
                    str(ident), self.pkg.name, self.pkg.version
                )
            )
            self.autopkg_msg(
                "Patch definition does not have version: %s"
                % self.pkg.version
            )
            exit()
        # update the patch def
        data = ET.tostring(root)
        self.logger.debug("About to put PST: %s" % url)
        ret = requests.put(url, auth=self.auth, data=data)
        if ret.status_code != 201:
            raise ProcessorError(
                "Patch definition update failed with code: %s"
                % ret.status_code
            )
        self.logger.debug("patch def updated")
        # now the patch policy - this will be a journey as well
        # first get the list of patch policies for our software title
        url = self.base + "patchpolicies/softwaretitleconfig/id/" + str(ident)
        self.logger.debug("About to request patch list: %s" % url)
        ret = requests.get(url, auth=self.auth)
        if ret.status_code != 200:
            raise ProcessorError(
                "Patch policy list download failed: {} : {}".format(
                    str(ident), self.pkg.name
                )
            )
        root = ET.fromstring(ret.text)
        # loop through policies for the Test one
        pol_list = root.findall("patch_policy")
        self.logger.debug("Got the PP list and name is: %s" % self.pkg.name)
        self.autopkg_msg("Updating patch policy: %s Test" % self.pkg.patch)
        for pol in pol_list:
            # now grab policy
            self.logger.debug(
                "examining patch policy %s" % pol.findtext("name")
            )
            if "Test" in pol.findtext("name"):
                pol_id = pol.findtext("id")
                url = self.base + "patchpolicies/id/" + str(pol_id)
                self.logger.debug("About to request PP by ID: %s" % url)
                ret = requests.get(url, auth=self.auth)
                if ret.status_code != 200:
                    raise ProcessorError(
                        "Patch policy download failed: {} : {}".format(
                            str(pol_id), self.pkg.name
                        )
                    )
                # now edit the patch policy
                root = ET.fromstring(ret.text)
                self.logger.debug(
                    "Got patch policy with version : %s : and we are : %s :"
                    % (
                        root.findtext("general/target_version"),
                        self.pkg.version,
                    )
                )
                if root.findtext("general/target_version") == self.pkg.version:
                    # we have already done this version
                    self.logger.debug(
                        "Version %s already done" % self.pkg.version
                    )
                    return 0
                root.find("general/target_version").text = self.pkg.version
                root.find("general/release_date").text = ""
                root.find("general/enabled").text = "true"
                # create a description with date
                now = datetime.datetime.now().strftime(" (%Y-%m-%d)")
                desc = "Update " + self.pkg.package + now
                root.find(
                    "user_interaction/self_service_description"
                ).text = desc
                data = ET.tostring(root)
                self.logger.debug("About to change PP: %s" % url)
                ret = requests.put(url, auth=self.auth, data=data)
                if ret.status_code != 201:
                    raise ProcessorError(
                        "Patch policy update failed with code: %s"
                        % ret.status_code
                    )
                pol_id = ET.fromstring(ret.text).findtext("id")
                self.logger.debug("patch() returning pol_id %s", pol_id)
                return pol_id
        raise ProcessorError("Test patch policy missing")

    def main(self):
        """Do it!"""
        self.setup_logging()
        self.logger.debug("Starting Main")
        # clear any pre-exising summary result
        if "patch_manager_summary_result" in self.env:
            del self.env["patch_manager_summary_result"]
        self.logger.debug("About to update package")
        self.pkg.package = self.env.get("package")
        try:
            self.pkg.patch = self.env.get("patch")
        except KeyError:
            self.pkg.patch = self.pkg.package
        self.autopkg_msg("Starting %s" % self.pkg.patch)

        # test_weekdays, if not set the default is ""
        self.pkg.test_weekdays = self.env.get("test_weekdays", "")
        self.logger.debug("Set self.pkg.test_weekdays: %s", self.pkg.test_weekdays)
        if self.pkg.test_weekdays == "":
            log_msg = "ANY"
        else:
            log_msg = self.pkg.test_weekdays
        self.autopkg_msg(
            "Testing only on weekday(s): %s "
            % log_msg
        )

        # test_not_before, if not set the default is ""
        self.pkg.test_not_before = self.env.get("test_not_before", "")
        self.logger.debug("Set self.pkg.test_not_before: %s", self.pkg.test_not_before)
        if self.pkg.test_not_before == "":
            log_msg = "ANY"
        else:
            log_msg = self.pkg.test_not_before
        self.autopkg_msg(
            "Production not before time: %s "
            % log_msg
        )

        # test_not_after, if not set the default is ""
        self.pkg.test_not_after = self.env.get("test_not_after", "")
        self.logger.debug("Set self.pkg.test_not_after: %s", self.pkg.test_not_after)
        if self.pkg.test_not_after == "":
            log_msg = "ANY"
        else:
            log_msg = self.pkg.test_not_after
        self.autopkg_msg(
            "Production not before time: %s "
            % log_msg
        )

        # Is it time to move to testing?
        if not self.time_for_testing():
            self.logger.debug("Time for test = False :: ENDING")
            return

        self.pkg.version = self.policy()
        pol_id = self.patch()
        if pol_id != 0:
            self.env["patch_manager_summary_result"] = {
                "summary_text": "The following packages were sent to test:",
                "report_fields": ["patch_id", "package", "version"],
                "data": {
                    "patch_id": pol_id,
                    "package": self.pkg.package,
                    "version": self.pkg.version,
                },
            }
            self.autopkg_msg(
                "%s version %s sent to test"
                % (self.pkg.package, self.pkg.version)
            )
        else:
            self.logger.debug("Zero policy id %s" % self.pkg.patch)


if __name__ == "__main__":
    PROCESSOR = PatchManager()
    PROCESSOR.execute_shell()
