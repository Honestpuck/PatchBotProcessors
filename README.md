# PatchBotProcessors
Part of PatchBot - three AutoPkg custom processors

Details can be found at https://github.com/Honestpuck/PatchBot



## MetroEast is working towards changes to PatchBot allowing all execution be to managed in AutoPkgr.app using custom recipes.  The intended result is to remove the need for additional scripts, a .ptch recipe, launchd triggering, and text file editing.

## Branch mvp-3 is our edit for consideration.

### Example recipes and templates can be seen here:
- https://github.com/metroeast/metroeast-recipes/

**GoogleChrome.jpci is a Jamf Pro Cloud Importer recipe**<br>
.jpci recipes call all PatchBot processors in order:
- JPCImporter.py
- PatchManager.py
- Production.py

Optional recipe input arguments, provide scheduling controls; along with the main AutoPkg run cycle configuration (launchd settings).  When empty, the criteria is treated as "ANY" day or time, and no delay or 0 days between test and production.

Recipes can specify the weekdays and hours, when a move to testing is allowed to happen.
- PM_TEST_WEEKDAYS
- PM_TEST_NOT_BEFORE
- PM_TEST_NOT_AFTER

Recipes can specify the minimum days before moving from test to production.
- PM_MIN_DAYS_FROM_TEST_TO_PROD

Recipes can specify the weekdays and hours, when a move to production is allowed to happen.
- PM_PROD_WEEKDAYS
- PM_PROD_NOT_BEFORE
- PM_PROD_NOT_AFTER

When specified, the above criteria must be met before the process will proceed.

Current time and date are used to check against the arguments provided.

The …_WEEKDAYS arguments can include any of the the numbers 0 through 6 as a string, which represent Monday through Sunday, respectively.
> For example: Mon, Tue, Wed, and Thu == "0123"

The …_NOT_BEFORE and …_NOT_AFTER are 24 hour time strings, HH:MM format.

Production.py has been modified to use logic similar to PatchBotTools/Move.py

The current date is compared to the date posted in the user interaction description, of the "[App Name] Test" patch policy associated with the patch software title.<br>
If the difference is >= the 'days to production' argument, the package is moved to production.
> [App Name] is matched from the argument PATCH

**GoogleChrome.prod is a JPCI utility recipe**<br>
.prod recipes call only the Production processor, and will "move to production" without delay.  This recipe omits the new arguments.  When any are omitted those criteria are skipped.  ***Omitting arguments from an override will accept any default values present in the base recipe, and is not recommended, due to lack of clarity.***

The package info is read from the policy, "Test-[Package Filename w/o version and extension]"
> [Package Filename…] is matched from the argument PACKAGE

This is then attached to the policy "Install [Package Filename w/o version and extension]" and
  the patch policy "[App Name] Stable"

.ptch recipes are deprecated

