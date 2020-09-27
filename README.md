# PatchBotProcessors
Part of PatchBot - three AutoPkg custom processors

Details can be found at https://github.com/Honestpuck/PatchBot



## MetroEast is working towards changes to PatchBot allowing all execution be to managed in AutoPkg recipes.  The intended result is to remove the need for additional scripts, a .ptch recipe, launchd triggering, and text file editing.

## Branch mvp-3 is our edit for consideration.

### Example recipes can be seen here:
- https://github.com/metroeast/metroeast-recipes/tree/master/GoogleChrome

**GoogleChrome.jpci is a Jamf Pro Cloud Importer recipe**<br>
.jpci recipes call all PatchBot processors in order:
- JPCImporter.py
- PatchManager.py
- Production.py

A recipe can specify the days in test, before move to production.  This is managed by specifying an integer in the arguments of the Production processor section of a recipe.
- days_until_prod

A recipe can specify the weekdays and hours, when a move to production is allowed to happen.
- prod_weekdays
- prod_not_before
- prod_not_after

When specified, the above criteria must be met before the process will proceed.

Current time and date are used to check against weekdays, not before time, and not after time.

The prod_weekdays argument can include any of the the numbers 0 through 6 as a string, which represent Monday through Sunday, respectively.
> For example: Mon, Tue, Wed, and Thu == "0123"

The prod_not_before and prod_not_after are 24 hour time strings, HH:MM format.

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

