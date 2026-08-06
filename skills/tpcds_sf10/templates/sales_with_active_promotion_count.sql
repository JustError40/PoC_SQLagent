SELECT COUNT(*) FROM catalog_sales cs JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk WHERE p.p_promo_sk IS NOT NULL;
