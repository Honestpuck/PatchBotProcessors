#!/usr/bin/env python3
#
# Production v3.0b
# Tony Williams 2020-12-22
#
# ARW 2020-06-25 Code clean up
# ARW 2020-07-07 Straighten logic for autopkg report
# ARW 2020-12-22 First hack at version 3

"""See docstring for Production class"""

from os import path
import plistlib
import xml.etree.ElementTree as ET
import datetime
import logging.handlers
import requests

from autopkglib import Processor, ProcessorError

APPNAME = "Production"
LOGLEVEL = logging.DEBUG

# default number of days a package spends in Test
DEFAULT_DELTA = 7

# default for self service deadline (days)
DEFAULT_DEADLINE = 7


__all__ = [APPNAME]


class Package:
    """A package. This exists merely to carry the variables"""

    # the application title from package name matching the test policy
    package = ""
    patch = ""  # name of the patch definition
    name = ""  # full name of the package '<package>-<version>.pkg'
    version = ""  # the version of our package
    idn = ""  # id of the package in our JP server


class Production(Processor):
    """Moves a package from testing to production by disabling the test
    policy, changing the production policy to use the new package, and
    creating a patch policy
    """

    description = __doc__

    input_variables = {
        "package": {"required": True, "description": "Package name"},
        "patch": {"required": False, "description": "Patch name"},
        "delta": {"required": False, "description": "Days in test"},
    }

    output_variables = {
        "production_summary_result": {"description": "Summary of action"}
    }

    # a package
    pkg = Package()

    def load_prefs(self):
        """ load the preferences from file """
        # Which pref format to use, autopkg or jss_importer
        autopkg = True
        if autopkg:
            plist = path.expanduser(
                "~/Library/Preferences/com.github.autopkg.plist"
            )
            prefs = plistlib.load(open(plist, "rb"))
            url = prefs["JSS_URL"]
            auth = (prefs["API_USERNAME"], prefs["API_PASSWORD"])
        else:
            plist = path.expanduser("~/Library/Preferences/JPCImporter.plist")
            prefs = plistlib.load(open(plist, "rb"))
            url = prefs["url"]
            auth = (prefs["user"], prefs["password"])
        base = url + "/JSSResource"
        # some API calls we want the JSON. NOTE: Since the API defaults to XML
        # we can just not pass headers for those calls and we get the XML
        self.hdrs = {"accept": "application/json"}
        return (base, auth)

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

    def check_delta(self):
        now = datetime.datetime.now()
        name = f"{self.pkg.patch} Test"
        self.logger.debug(f"About to policy_list, name: {name}")
        policies = self.policy_list()
        self.logger.debug("done policy_list")
        try:
            policy_id = policies[name]
        except KeyError:
            raise ProcessorError(
                "Test policy key missing: {}".format(name)
            )
        self.logger.debug(f"Got valid policy id: {policy_id}")
        policy = self.policy(str(policy_id))
        # self.logger.debug(f"back from policy(): {policy}")
        if policy['general']['enabled'] == False:
            self.logger.debug("TEST patch policy disabled")
            return False
        else:
            self.logger.debug(f"['general']['enabled'] :{policy['general']['enabled']}")
        description = policy["user_interaction"][
                    "self_service_description"
                ].split()
        # we may have found a patch policy with no proper description yet
        if len(description) != 3:
            return(False)
        title, datestr = description[1:]

        date = datetime.datetime.strptime(datestr, "(%Y-%m-%d)")
        delta = now - date
        self.logger.debug(f"    Description:{description}")
        self.logger.debug(f"    Datestr    :{datestr}")
        self.logger.debug(f"    Date       :{date}")
        self.logger.debug(f"    Delta      :{delta.days}")
        self.logger.debug(f"    PkgDelta   :{self.pkg.delta}")

        if delta.days >= self.pkg.delta:
            return(True)
        return(False)

    def lookup(self):
        """look up test policy to find package name, id and version """
        self.logger.debug("Starting")
        url = self.base + "/policies/name/Test-" + self.pkg.package
        pack_base = "package_configuration/packages/package"
        self.logger.debug("About to request %s", url)
        ret = requests.get(url, auth=self.auth, cookies=self.cookies)
        if ret.status_code != 200:
            raise ProcessorError(
                "Test policy download failed: {} : {}".format(
                    ret.status_code, url
                )
            )
        policy = ET.fromstring(ret.text)
        test_id = policy.findtext("general/id")
        self.logger.debug("Got test policy id %s", test_id)
        self.pkg.idn = policy.findtext(pack_base + "/id")
        self.pkg.name = policy.findtext(pack_base + "/name")
        self.pkg.version = self.pkg.name.split("-", 1)[1][:-4]

    def production(self):
        """change the package in the production policy"""
        url = self.base + "/policies/name/Install " + self.pkg.package
        pack_base = "package_configuration/packages/package"
        self.logger.debug("About to request %s", url)
        ret = requests.get(url, auth=self.auth, cookies=self.cookies)
        self.logger.debug("After get status: %i", ret.status_code)
        if ret.status_code != 200:
            raise ProcessorError(
                "Prod policy download failed: {} : {}".format(
                    ret.status_code, url
                )
            )
        prod = ET.fromstring(ret.text)
        self.logger.debug(f"Prod: {prod}")
        self.logger.debug("Parsed XML from Install policy")
        prod.find("general/id").text = self.pkg.idn
        self.logger.debug("Got ID from Install")
        prod.find("general/name").text = self.pkg.name
        self.logger.debug("Got name from Install")
        data = ET.tostring(prod)
        self.logger.debug("Parsed to XML for Install")
        self.logger.debug("About to put install policy %s", url)
        ret = requests.put(url, auth=self.auth, 
            data=data, cookies=self.cookies)
        if ret.status_code != 201:
            raise ProcessorError(
                "Prod policy upload failed: {} : {}".format(
                    ret.status_code, url
                )
            )

    def patch(self):
        """now we start on the patch definition"""
        # download the list of titles
        url = self.base + "/patchsoftwaretitles"
        ret = requests.get(url, auth=self.auth, cookies=self.cookies)
        patch_def_software_version = ""
        self.logger.debug("About to request PST list %s", url)
        if ret.status_code != 200:
            raise ProcessorError(
                "Patch list download failed: {} : {}".format(
                    ret.status_code, url
                )
            )
        root = ET.fromstring(ret.text)
        # find title to get ID
        root.findall("patch_software_title")
        pst_id = 0
        for ps_title in root.findall("patch_software_title"):
            if ps_title.findtext("name") == self.pkg.patch:
                pst_id = ps_title.findtext("id")
                break
        if pst_id == 0:
            raise ProcessorError(
                "Patch list did not contain title: {}".format(self.pkg.package)
            )
        # get patch list for our title
        url = self.base + "/patchsoftwaretitles/id/" + str(pst_id)
        self.logger.debug("About to request PST by ID: %s", url)
        ret = requests.get(url, auth=self.auth, cookies=self.cookies)
        if ret.status_code != 200:
            raise ProcessorError(
                "Patch software download failed: {} : {}".format(
                    str(pst_id), self.pkg.name
                )
            )
        root = ET.fromstring(ret.text)
        # find the patch version that matches our version
        done = False
        for record in root.findall("versions/version"):
            if self.pkg.version in record.findtext("software_version"):
                patch_def_software_version = record.findtext("software_version")
                package = record.find("package")
                add = ET.SubElement(package, "id")
                add.text = self.pkg.idn
                add = ET.SubElement(package, "name")
                add.text = self.pkg.name
                done = True
                break
        if not done:
            raise ProcessorError(
                "Patch definition version not found: {} : {} : {}".format(
                    str(pst_id), self.pkg.name, self.pkg.version
                )
            )
        # update the patch def
        data = ET.tostring(root)
        self.logger.debug("About to put PST: %s", url)
        ret = requests.put(url, auth=self.auth, data=data, cookies=self.cookies)
        if ret.status_code != 201:
            raise ProcessorError(
                "Patch definition update failed with code: %s"
                % ret.status_code
            )
        # now the patch policy - this will be a journey as well
        # first get the list of patch policies for our software title
        url = (
            self.base + "/patchpolicies/softwaretitleconfig/id/" + str(pst_id)
        )
        self.logger.debug("About to request patch list: %s", url)
        ret = requests.get(url, auth=self.auth)
        if ret.status_code != 200:
            raise ProcessorError(
                "Patch policy list download failed: {} : {}".format(
                    str(pst_id), self.pkg.name
                )
            )
        root = ET.fromstring(ret.text)
        pol_list = root.findall("patch_policy")
        for pol in pol_list:
            if "Stable" in pol.findtext("name"):
                pol_id = pol.findtext("id")
                # now grab that policy
                url = self.base + "/patchpolicies/id/" + str(pol_id)
                self.logger.debug("About to request Stable PP by ID: %s", url)
                ret = requests.get(url, auth=self.auth, cookies=self.cookies)
                if ret.status_code != 200:
                    raise ProcessorError(
                        "Patch policy download failed: {} : {}".format(
                            str(pol_id), self.pkg.name
                        )
                    )
                # now edit the patch policy
                root = ET.fromstring(ret.text)
                root.find("general/target_version").text = patch_def_software_version
                root.find("general/release_date").text = ""
                root.find("user_interaction/deadlines/deadline_period"
                    ).text = str(self.pkg.deadline)
                # create a description with date
                now = datetime.datetime.now().strftime(" (%Y-%m-%d)")
                root.find(
                    "user_interaction/self_service_description"
                    ).text =  "Update " + self.pkg.package + now
                data = ET.tostring(root)
                self.logger.debug("About to update Stable PP: %s", url)
                ret = requests.put(url, auth=self.auth, 
                    data=data, cookies=self.cookies)
                if ret.status_code != 201:
                    raise ProcessorError(
                        "Stable patch update failed with code: %s"
                        % ret.status_code
                    )
            if "Test" in pol.findtext("name"):
                pol_id = pol.findtext("id")
                # now grab that policy
                url = self.base + "/patchpolicies/id/" + str(pol_id)
                self.logger.debug("About to request Test PP by ID: %s URL: %s", str(pol_id), url)
                ret = requests.get(url, auth=self.auth, cookies=self.cookies)
                if ret.status_code != 200:
                    raise ProcessorError(
                        "Patch policy download failed: {} : {}".format(
                            str(pol_id), self.pkg.name
                        )
                    )
                # now disable the patch policy
                root = ET.fromstring(ret.text)
                root.find("general/enabled").text = "false"
                data = ET.tostring(root)
                self.logger.debug("About to update Test PP: %s", url)
                ret = requests.put(url, auth=self.auth, 
                    data=data, cookies=self.cookies)
                if ret.status_code != 201:
                    raise ProcessorError(
                        "Test patch update failed with code: %s"
                        % ret.status_code
                    )

    def policy_list(self):
        """ get the list of patch policies from JP and turn it into a dictionary """

        # let's use the cookies to make sure we hit the
        # same server for every request.
        # the complication here is that ordinary and Premium Jamfers
        # get two DIFFERENT cookies for this.

        # the front page will give us the cookies
        r = requests.get(self.base)
        cookie_value = r.cookies.get('APBALANCEID')
        if cookie_value:
            # we are NOT premium Jamf Cloud
            self.cookies = dict(APBALANCEID=cookie_value)
            c_cookie = "APBALANCEID=%s", cookie_value
            self.logger.debug("APBALANCEID found")
        else:
            cookie_value = r.cookies['AWSALB']
            self.cookies = dict(AWSALB=cookie_value)
            c_cookie = "AWSALB=%s", cookie_value
            self.logger.debug("APBALANCEID not found")

        url = self.base + "/patchpolicies"
        ret = requests.get(url, auth=self.auth, headers=self.hdrs, cookies=self.cookies)
        self.logger.debug("GET policy list url: %s status: %s" % (url, ret.status_code))
        if ret.status_code != 200:
            raise ProcessorError("GET failed URL: %s Err: %s" % (url, ret.status_code))
        # turn the list into a dictionary keyed on the policy name
        d = {}
        for p in ret.json()["patch_policies"]:
            d[p["name"]] = p["id"]
        return d

    def policy(self, idn):
        """ get a single patch policy """
        url = self.base + "/patchpolicies/id/" + idn
        ret = requests.get(url, auth=self.auth, headers=self.hdrs, cookies=self.cookies)
        self.logger.debug("GET policy url: %s status: %s" % (url, ret.status_code))
        if ret.status_code != 200:
            raise self.Error("GET failed URL: %s Err: %s" % (url, ret.status_code))
        self.logger.debug("About to return from policy")
        return ret.json()["patch_policy"]

    def main(self):
        """Do it!"""
        self.setup_logging()
        (self.base, self.auth) = self.load_prefs()
        # clear any pre-exising summary result
        if "production_summary_result" in self.env:
            self.logger.debug("Clearing prev summary")
            del self.env["prod_summary_result"]
        self.pkg.package = self.env.get("package")
        self.pkg.patch = self.env.get("patch")
        self.pkg.delta = self.env.get("delta")
        if self.pkg.delta:
            self.pkg.delta = int(self.pkg.delta)
        else:
            self.pkg.delta = 0
        deadline = self.env.get("deadline")
        self.logger.debug(f"Starting package {self.pkg.package}")
        self.logger.debug(f"get. delta: {self.pkg.delta}")
        if not self.pkg.delta:
            self.pkg.delta = DEFAULT_DELTA
        if deadline:
            self.pkg.deadline = int(deadline)
            self.logger.debug("Found deadline %i", self.pkg.deadline)
        else:
            self.pkg.deadline = DEFAULT_DEADLINE
        if not self.pkg.patch:
            self.pkg.patch = self.pkg.package
        if self.check_delta():
            self.logger.debug("Passed delta. Package: %s", self.pkg.package)
            self.lookup()
            self.production()
            self.logger.debug("Post production self.pkg.patch: %s", self.pkg.patch)
            self.patch()
            self.logger.debug("Done patch")
            self.env["production_summary_result"] = {
                "summary_text": "The following updates were productionized:",
                "report_fields": ["package", "version"],
                "data": {"package": self.pkg.package, "version": self.pkg.version,},
            }
            self.logger.debug(
                "Summary done: %s" % self.env["production_summary_result"]
            )


if __name__ == "__main__":
    PROCESSOR = Production()
    PROCESSOR.execute_shell()
