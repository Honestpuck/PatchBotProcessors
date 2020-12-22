# PatchBotProcessors
Part of PatchBot - three AutoPkg custom processors

Details can be found at https://github.com/Honestpuck/PatchBot

This the v3 branch. It is now in active development while the main branch has halted apart from bug fixes (if required 🤞).

Changes can be summarised:
    - replaced the need for Move.py. All the checking to see if there is a test patch to move into production is now done in the Production processor
    - There is a new variable in the Production processor code, `DEFAULT_DELTA` to set the default number of days between test and production
    - There is a new optional variable in Production `.prod` recipes called `delta` to set the number of days between test and production for that one package
  
The code *should* run but it is beta. Certainly the Production processor could be cleaned up as it it grabs information to check the delta then throws it all away so the process to move a package from test into production has to find it all again, that's less than optimal and makes unnecessary API calls.
