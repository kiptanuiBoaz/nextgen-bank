#!/bin/bash

# exit is there is a none 0 exit code
set -o errexit


#consider the pipe to have failed if any of the commands fail
set -o pipefail


#exit if there is an attempt to use an undefined variable
set -o nounset

python << END
import sys
import time
import psycopg2
suggest_unrecoverable_after = 30
start = time.time()
while True:
  try:
    psycopg2.connect(
      dbname="${POSTGRES_DB}",
      user="${POSTGRES_USER}",
      password="${POSTGRES_PASSWORD}",
      host="${POSTGRES_HOST}",
      port="${POSTGRES_PORT}",
    )
    break
  except psycopg2.OperationalError as error:
    sys.stderr.write("Waiting for PostgreSQL to become available...\n")
    if time.time() - start > suggest_unrecoverable_after:
      sys.stderr.write(
        "This is taking longer than expected. The following exception may be "
        "indicative of an unrecoverable error: '{}'\n".format(error)
      )
    time.sleep(3)
END

echo >&2 'PostgreSQL is available'

exec "$@"