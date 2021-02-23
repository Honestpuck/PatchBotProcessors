# PatchBotProcessors
Part of PatchBot - three AutoPkg custom processors

Details can be found at https://github.com/Honestpuck/PatchBot

This v3. It has now been released to production.

Changes can be summarised:

 - replaced the need for Move.py. All the checking to see if there is a test patch to move into production is now done in the Production processor
 - There is a new variable in the Production processor code, `DEFAULT_DELTA` to set the default number of days between test and production
 - There is a new optional variable in Production `.prod` recipes called `delta` to set the number of days between test and production for that one package
  
The code *should* run, it has been vigorously tested. There are still things to be done. Certainly the Production processor could be cleaned up as it it grabs information to check the delta then throws it all away so the process to move a package from test into production has to find it all again, that's less than optimal and makes unnecessary API calls.

Now that `delta` can be defined in a `.prod` recipe it is now possible to move a package from test into production from the command line. `autopkg run GoogleChrome.prod -k 'delta=0'` will immediately move Google Chrome from testing into production, for example.
