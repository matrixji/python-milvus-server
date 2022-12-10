#!/bin/bash

## variables

MILVUS_REPO=${MILVUS_REPO:-https://github.com/matrixji/milvus.git}
MILVUS_BRANCH=${MILVUS_BRANCH:-2.2.0}


set -e

BUILD_FORCE=NO

cd $(dirname $0)

# getopts
while getopts "f" arg; do
    case $arg in
        f)
            BUILD_FORCE=YES
        ;;
        *)
        ;;
    esac
done

if [[ ${BUILD_FORCE} == "YES" ]] ; then
    rm -fr milvus
fi

# clone milvus
if [[ ! -d milvus ]] ; then
    git clone --branch ${MILVUS_BRANCH} ${MILVUS_REPO} --depth 1
fi


cd milvus
bash scripts/install_deps_msys.sh
source scripts/setenv.sh

# this is needed when first install golang without restarting the shell
export GOROOT=/mingw64/lib/go
go version

make milvus

# resolve all dll for milvus.exe
cd bin
mv milvus milvus.exe

find .. -name \*.dll | xargs -I {} cp -frv {} . || :
for x in $(ldd milvus.exe | awk '{print $1}') ; do
    if [ -f ${MINGW_PREFIX}/bin/$x ] ; then
        cp -frv ${MINGW_PREFIX}/bin/$x .
    fi
done
