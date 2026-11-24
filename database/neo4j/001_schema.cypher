CYPHER 5 CREATE CONSTRAINT bucket_user_key IF NOT EXISTS FOR (n:User) REQUIRE n.key IS UNIQUE;
CYPHER 5 CREATE CONSTRAINT bucket_product_key IF NOT EXISTS FOR (n:Product) REQUIRE n.key IS UNIQUE;
CYPHER 5 CREATE CONSTRAINT bucket_image_key IF NOT EXISTS FOR (n:Image) REQUIRE n.key IS UNIQUE;
CYPHER 5 CREATE CONSTRAINT bucket_category_key IF NOT EXISTS FOR (n:Category) REQUIRE n.key IS UNIQUE;
CYPHER 5 CREATE CONSTRAINT bucket_order_key IF NOT EXISTS FOR (n:Order) REQUIRE n.key IS UNIQUE;
CYPHER 5 CREATE CONSTRAINT bucket_orderitem_key IF NOT EXISTS FOR (n:OrderItem) REQUIRE n.key IS UNIQUE;
CYPHER 5 CREATE CONSTRAINT bucket_review_key IF NOT EXISTS FOR (n:Review) REQUIRE n.key IS UNIQUE;
CYPHER 5 CREATE FULLTEXT INDEX image_metadata_text IF NOT EXISTS
FOR (i:Image) ON EACH [i.search_text,i.search_text_folded]
OPTIONS {indexConfig: {`fulltext.analyzer`: 'standard-no-stop-words'}};
