SELECT DISTINCT frpm."School Name" FROM frpm JOIN satscores ON frpm.cdscode = satscores.cds WHERE frpm."Percent (%) Eligible Free (K-12)" > 0.1 AND satscores.numge1500 > 0;
