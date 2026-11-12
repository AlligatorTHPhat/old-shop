-- index-catalog: index-v2-fragmentation 125d9b89525872562a16487acf71ead0d76404267abf4819c33989d7234a9784
-- Additive seller catalogue index; transactional runner, no concurrent DDL.
CREATE INDEX "idx_product_visible_seller_date_id" ON "public"."product" USING btree ("seller_id" ASC NULLS LAST, "created_at" DESC NULLS FIRST, "product_id" ASC NULLS LAST) WHERE (("status" = 1) AND ("is_deleted" = FALSE));
