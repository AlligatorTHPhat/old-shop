#!/bin/sh
set -eu
: "${MINIO_APP_ACCESS_KEY:?}" "${MINIO_APP_SECRET_KEY:?}"
export MC_CONFIG_DIR=/tmp/oldshop-mc
mc alias set store http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
for bucket in product-images user-avatars attachments; do
  mc mb --ignore-existing "store/$bucket" >/dev/null
  mc anonymous set none "store/$bucket" >/dev/null
done
cat > /tmp/oldshop-media-policy.json <<'JSON'
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["s3:GetBucketLocation","s3:ListBucket"],"Resource":["arn:aws:s3:::product-images","arn:aws:s3:::user-avatars","arn:aws:s3:::attachments"]},
 {"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject"],"Resource":["arn:aws:s3:::product-images/*","arn:aws:s3:::user-avatars/*","arn:aws:s3:::attachments/*"]}
]}
JSON
mc admin policy create store oldshop-media /tmp/oldshop-media-policy.json >/dev/null
if ! mc admin user info store "$MINIO_APP_ACCESS_KEY" >/dev/null 2>&1; then
  mc admin user add store "$MINIO_APP_ACCESS_KEY" "$MINIO_APP_SECRET_KEY" >/dev/null
fi
mc admin policy attach store oldshop-media --user "$MINIO_APP_ACCESS_KEY" >/dev/null
mc alias set application http://minio:9000 "$MINIO_APP_ACCESS_KEY" "$MINIO_APP_SECRET_KEY" >/dev/null
mc ls application/product-images >/dev/null
echo 'Private buckets and bucket-scoped application user ready.'
