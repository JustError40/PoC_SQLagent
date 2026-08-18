SELECT satscores.rtype, AVG(satscores.numtsttakr) FROM satscores GROUP BY satscores.rtype;
