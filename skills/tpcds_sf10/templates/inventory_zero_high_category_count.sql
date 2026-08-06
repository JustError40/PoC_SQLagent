SELECT COUNT(*) FROM public.inventory i JOIN public.item it ON i.inv_item_sk = it.i_item_sk WHERE i.inv_quantity_on_hand = 0 AND it. i_category = 'high';
