#!/usr/bin/env python3
#
# Production v2.1.1
# Tony Williams 2020-05-24
# David Elkin-Bram 2020-09-21
#
# ARW 2020-06-25 Code clean up
# ARW 2020-07-07 Straighten logic for autopkg report
# MVP-3 2020-09-21 Incorporate Move.py date logic, adding new recipe variable

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


__all__ = [APPNAME]


class Package:
    """A package. This exists merely to carry the variables"""

    # the application title from package name matching the test policy
    package = ""
    patch = ""  # name of the patch definition
    name = ""  # full name of the package '<package>-<version>.pkg'
    version = ""  # the version of our package
    idn = ""  # id of the package in our JP server
    days_to_production = ""  # days before move to production


class Production(Processor):
    """Moves a package from testing to production by disabling the test
    policy, changing the production policy to use the new package, and
    creating a patch policy
    """

    description = __doc__

    input_variables = {
        "package": {"required": True, "description": "Package name"},
        "patch": {"required": False, "description": "Patch name"},
        "days_to_production": {"required": False, "description": "Days before move to production"},
    }

    output_variables = {
        "production_summary_result": {"description": "Summary of action"}
    }

    # a package
    pkg = Package()

    def load_prefs(self):
        """ load the preferences from file """
        # Which pref format to use, autopkg or jss_importer
        autopkg = False
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

    ## code here could be optimized
    ## somewhat redundant lookups happening in later routines
    def time_to_move(self):
        """test whether or not to move to production"""
        self.logger.debug("Move Check")
        if int(self.pkg.days_to_production) == 0:
            self.logger.debug("Moving Now")
            return True

        # we will parse the patch policy as in PatchManager.py:patch()
        # download the list of titles
        url = self.base + "/patchsoftwaretitles"
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
        
        # first get the list of patch policies for our software title
        url = self.base + "/patchpolicies/softwaretitleconfig/id/" + str(ident)
        self.logger.debug("About to request patch list: %s" % url)
        ret = requests.get(url, auth=self.auth)
        if ret.status_code != 200:
            ## self.pkg.name -> self.pkg.package
            raise ProcessorError(
                "Patch policy list download failed: {} : {}".format(
                    str(ident), self.pkg.package
                )
            )
        root = ET.fromstring(ret.text)
        # loop through policies for the Test one
        pol_list = root.findall("patch_policy")
        ## self.pkg.name -> self.pkg.package
        self.logger.debug("Got the PP list and name is: %s" % self.pkg.package)
        for pol in pol_list:
            # now grab policy
            self.logger.debug(
                "examining patch policy %s" % pol.findtext("name")
            )
            if "Test" in pol.findtext("name"):
                pol_id = pol.findtext("id")
                url = self.base + "/patchpolicies/id/" + str(pol_id)
                self.logger.debug("About to request PP by ID: %s" % url)
                ret = requests.get(url, auth=self.auth)
                if ret.status_code != 200:
                    raise ProcessorError(
                        "Patch policy download failed: {} : {}".format(
                            str(pol_id), self.pkg.name
                        )
                    )
                # read the patch policy
                root = ET.fromstring(ret.text)
                self.logger.debug("TEST root: %s" % ret.text)
                
                now = datetime.datetime.now()
                self.logger.debug("TEST now: %s" % now)
                #now = datetime.datetime.now().strftime(" (%Y-%m-%d)")
                
                description = root.find(
                    "user_interaction/self_service_description"
                ).text.split()
                self.logger.debug("TEST description: %s" % description)
                
                # we may have found a patch policy with no proper description yet
                # unclear why we're testing the length not equal to 3
                if len(description) != 3:
                    self.logger.debug("Date not understood, skipping.")
                    return False
                
                title, datestr = description[1:]
                self.logger.debug("TEST title: %s" % title)
                self.logger.debug("TEST datestr: %s" % datestr)
                
                date = datetime.datetime.strptime(datestr, "(%Y-%m-%d)")
                delta = now - date
                self.logger.debug(
                    "Found delta to check: %s in %s" % (delta.days, title)
                )
                if delta.days >= int(self.pkg.days_to_production):
                    self.logger.debug(
                        "%s Days delta >= %s Days before move, moving now."
                        % (delta.days, self.pkg.days_to_production)
                    )
                    return True
                else:
                    self.logger.debug(
                        "%s Days delta < %s Days before move, skipping move to production."
                        % (delta.days, self.pkg.days_to_production)
                    )
                    return False
                    
        raise ProcessorError("Test patch policy missing")
        
    def lookup(self):
        """look up test policy to find package name, id and version """
        self.logger.debug("Lookup")
        url = self.base + "/policies/name/Test-" + self.pkg.package
        pack_base = "package_configuration/packages/package"
        self.logger.debug("About to request %s", url)
        ret = requests.get(url, auth=self.auth)
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
        ret = requests.get(url, auth=self.auth)
        if ret.status_code != 200:
            raise ProcessorError(
                "Prod policy download failed: {} : {}".format(
                    ret.status_code, url
                )
            )
        prod = ET.fromstring(ret.text)
        prod.find(pack_base + "/id").text = self.pkg.idn
        prod.find(pack_base + "/name").text = self.pkg.name
        data = ET.tostring(prod)
        self.logger.debug("About to put install policy %s", url)
        ret = requests.put(url, auth=self.auth, data=data)
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
        ret = requests.get(url, auth=self.auth)
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
        ret = requests.get(url, auth=self.auth)
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
            if record.findtext("software_version") == self.pkg.version:
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
        ret = requests.put(url, auth=self.auth, data=data)
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
                self.logger.debug("About to request PP by ID: %s", url)
                ret = requests.get(url, auth=self.auth)
                if ret.status_code != 200:
                    raise ProcessorError(
                        "Patch policy download failed: {} : {}".format(
                            str(pol_id), self.pkg.name
                        )
                    )
                # now edit the patch policy
                root = ET.fromstring(ret.text)
                root.find("general/target_version").text = self.pkg.version
                root.find("general/release_date").text = ""
                # create a description with date
                now = datetime.datetime.now().strftime(" (%Y-%m-%d)")
                desc = "Update " + self.pkg.package + now
                root.find(
                    "user_interaction/self_service_description"
                ).text = desc
                data = ET.tostring(root)
                self.logger.debug("About to update Stable PP: %s", url)
                ret = requests.put(url, auth=self.auth, data=data)
                if ret.status_code != 201:
                    raise ProcessorError(
                        "Stable patch update failed with code: %s"
                        % ret.status_code
                    )
            if "Test" in pol.findtext("name"):
                pol_id = pol.findtext("id")
                # now grab that policy
                url = self.base + "/patchpolicies/id/" + str(pol_id)
                self.logger.debug("About to request PP by ID: %s", url)
                ret = requests.get(url, auth=self.auth)
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
                ret = requests.put(url, auth=self.auth, data=data)
                if ret.status_code != 201:
                    raise ProcessorError(
                        "Test patch update failed with code: %s"
                        % ret.status_code
                    )

    def main(self):
        """Do it!"""
        self.setup_logging()
        self.logger.debug("Starting")
        
        (self.base, self.auth) = self.load_prefs()
        # clear any pre-exising summary result
        if "production_summary_result" in self.env:
            self.logger.debug("Clearing prev summary")
            del self.env["prod_summary_result"]
        self.pkg.package = self.env.get("package")
        try:
            self.pkg.patch = self.env.get("patch")
        except KeyError:
            self.pkg.patch = self.pkg.package
        self.logger.debug("Set self.pkg.patch: %s", self.pkg.patch)
        
        if self.env.get("days_to_production"):
            self.pkg.days_to_production = self.env.get("days_to_production")
        else:
            self.pkg.days_to_production = "0"
        self.logger.debug("Set self.pkg.days_to_production: %s", self.pkg.days_to_production)
        
        if not self.time_to_move():
            self.logger.debug("Time to move = False :: ENDING")
            return
        
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
