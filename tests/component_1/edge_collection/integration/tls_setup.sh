#!/bin/sh
# Runs inside c1-pgtest only, as root. Throwaway CA + server cert for localhost,
# then TCP logins require TLS and a scram password (loopback included).
set -eu
mkdir -p /opt/c1/tls && cd /opt/c1/tls
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj '/CN=c1-synthetic-ca' \
  -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign' \
  -keyout ca.key -out ca.pem 2>/dev/null
openssl req -new -newkey rsa:2048 -nodes -subj '/CN=localhost' \
  -keyout server.key -out server.csr 2>/dev/null
printf 'subjectAltName=DNS:localhost,IP:127.0.0.1\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n' > server.ext
openssl x509 -req -days 1 -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial \
  -out server.crt -extfile server.ext 2>/dev/null
rm -f ca.key server.csr
chown postgres:postgres server.key server.crt ca.pem
chmod 0600 server.key && chmod 0644 server.crt ca.pem
openssl verify -CAfile ca.pem server.crt
hba=$(psql -U sim_admin -d postgres -Atc 'show hba_file')
sed -i -E 's#^host +all +all +(127\.0\.0\.1/32|::1/128) +trust$#hostssl all all \1 scram-sha-256#' "$hba"
sed -i -E 's#^host +all +all +all +scram-sha-256$#hostssl all all all scram-sha-256#' "$hba"
grep -E '^(host|hostssl|local)' "$hba"
psql -U sim_admin -d postgres -v ON_ERROR_STOP=1 -q \
  -c "ALTER SYSTEM SET ssl = on" \
  -c "ALTER SYSTEM SET ssl_cert_file = '/opt/c1/tls/server.crt'" \
  -c "ALTER SYSTEM SET ssl_key_file = '/opt/c1/tls/server.key'" \
  -c "SELECT pg_reload_conf()" >/dev/null
sleep 1
echo "ssl=$(psql -U sim_admin -d postgres -Atc 'show ssl')"
