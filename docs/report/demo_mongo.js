// mongosh hoặc MongoDB Compass Shell, trên DB demo đã chọn; chỉ đọc.
db.product_details.findOne({product_id: 1}, {
  _id: 0, product_id: 1, attributes: 1, tags: 1, images: 1, etl: 1
});
db.order_snapshots.findOne({order_id: 1}, {
  _id: 0, order_id: 1, items: 1, final_amount_vnd: 1, etl: 1
});
db.product_details.getIndexes();
db.system_logs.getIndexes(); // expireAfterSeconds=7776000; PG không bị purge.
db.adminCommand({hello: 1}); // setName/primary; không dùng để suy ra Mongo sharding.
