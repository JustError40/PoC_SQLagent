SELECT COUNT(*) AS "virtual_schools_count" FROM "schools" JOIN "satscores" ON "schools"."cdscode" = "satscores"."cds" WHERE "schools"."virtual" = '1' AND "satscores"."avgscrmath" > 400 LIMIT 1;
