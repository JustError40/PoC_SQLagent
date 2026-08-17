SELECT "schools"."school", "schools"."street" FROM "schools" JOIN "satscores" ON "schools"."cdscode" = "satscores"."cds" ORDER BY "satscores"."avgscrmath" DESC LIMIT 1 OFFSET 6;
