#!/bin/bash

## variables

MILVUS_REPO=${MILVUS_REPO:-https://github.com/matrixji/milvus.git}
MILVUS_COMMIT=${MILVUS_COMMIT:-674d932b8c3af36d5e1244e91c4f964c16aa0bc1}
BUILD_PROXY=

echo $BUILD_PROXY

set -e

BUILD_FORCE=NO

cd $(dirname $0)

# getopts
while getopts "fr:b:p:" arg; do
    case $arg in
        f)
            BUILD_FORCE=YES
        ;;
        r)
            MILVUS_REPO=$OPTARG
        ;;
        b)
            MILVUS_BRANCH=$OPTARG
        ;;
        p)
            BUILD_PROXY=$OPTARG
        ;;
        *)
        ;;
    esac
done


if [[ ${BUILD_FORCE} == "YES" ]] ; then
    rm -fr milvus
fi

if [[ "${BUILD_PROXY}" != "" ]] ; then
    export http_proxy=${BUILD_PROXY}
    export https_proxy=${BUILD_PROXY}
fi

# clone milvus
if [[ ! -d milvus ]] ; then
    git clone ${MILVUS_REPO} milvus
    cd milvus
    git checkout ${MILVUS_COMMIT}
    cd -
fi


# get host
OS=$(uname -s)
ARCH=$(uname -i)


## functions for each os

function build_msys() {
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
}

function build_linux_x86_64() {
    if [[ ${BUILD_ALREADY_IN_DOCKER} == "YES" ]] ; then
        set -e
        if [[ -d milvus ]] ; then
            cd milvus
        elif [[ -d /src/milvus ]] ; then
            cd /src/milvus
        fi
        make milvus
        cd bin
        rm -fr lib*
        strip milvus
        find .. -name \*.so | xargs -I {} cp -frv {} . || :
        find .. -name \*.so\.* | xargs -I {} cp -frv {} . || :

        for x in $(ldd milvus | awk "{print $1}") ; do
            if [[ $x =~ libc.* ]] ; then
                :
            elif [[ $x =~ libdl.* ]] ; then
                :
            elif [[ $x =~ libm.* ]] ; then
                :
            elif [[ $x =~ librt.* ]] ; then
                :
            elif [[ $x =~ libpthread.* ]] ; then
                :
            elif [[ $x =~ libstdc++.* ]] ; then
                :
            elif test -f $x ; then
                :
            else
                for p in /lib64 /usr/lib64 /usr/local/lib64 /usr/local/lib /usr/lib64/boost169 ; do
                    if test -f $p/$x && ! test -f $x ; then
                       file=$p/$x
                        while test -L $file ; do
                            file=$(dirname $file)/$(readlink $file)
                        done
                        cp -frv $file $x
                    fi
                done
            fi
        done
    else
        
        docker_build_proxys=
        docker_run_proxys=
        if [[ "$BUILD_PROXY" != "" ]] ; then
            docker_build_proxys=" --build-arg http_proxy=${BUILD_PROXY} --build-arg https_proxy=${BUILD_PROXY} "
            docker_run_proxys=" -e http_proxy=${BUILD_PROXY} -e https_proxy=${BUILD_PROXY} "
        fi
        # build docker for builder
        ## docker build -t python-milvus-server-builder:latest ${docker_build_proxys} tools/build-env-manylinux2014
        mkdir -p tmp
        docker run -u $(id -u):$(id -g) -e HOME=/tmp -e BUILD_ALREADY_IN_DOCKER=YES --rm ${docker_run_proxys} \
            -v$(pwd):/src \
            -v$(pwd)/tmp:/tmp \
            matrixji/python-milvus-server-builder:linux_x86_64_20221212 bash -c "cd /src && bash run-prebuild.sh"
    fi
}



case $OS in
    Linux)
        build_linux_${ARCH}
        ;;
    MINGW*)
        build_msys
        ;;
    *)
        ;;
esac

