#!/bin/bash

set -o pipefail
RESULT=0

LICENSE_FILES=$(git ls-files | \
    grep "build\|src\|proto" | \
    grep -e "\.proto\|\.rs\|\.ts" | \
    grep -v "quickwit-proto/protos/third-party" | \
    grep -v "quickwit-proto/src" | \
    grep -v "/codegen/" | \
    grep -v -E '(^|/)vendor/lru-(0\.16\.4|0\.17\.0)/src/lib\.rs$' \
) || exit 1

for file in $LICENSE_FILES
do
    diff <(sed 's/{\\d+}/2021/' .license_header.txt) <(head -n 14 $file) > /dev/null
    DIFFRESULT=$?
    if [ $DIFFRESULT -ne 0 ]; then
        grep -q -i 'begin quickwit-codegen' $file
        GREPRESULT=$?
        if [ $GREPRESULT -ne 0 ]; then
            echo "Incomplete or missing license header in $file"
            RESULT=1
        fi
    fi
done

exit $RESULT
