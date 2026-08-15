SELECT COUNT("satscores"."cds") AS "school_count" FROM "satscores" WHERE "satscores"."avgscrmath" > 400 AND "satscores"."rtype" = 'virtual' ORDER BY "school_count" DESC;
