#!/bin/bash

## variables

MILVUS_REPO=${MILVUS_REPO:-https://github.com/milvus-io/milvus.git}
MILVUS_COMMIT=${MILVUS_COMMIT:-9b8f04fd84840cfeb180a4e723ba2d1f2c8809bd}
MILVUS_PATCH_NAME=${MILVUS_PATCH_NAME:-master}
BUILD_PROXY=

export LANG=en_US.utf-8
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

echo using proxy during build: $BUILD_PROXY


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
    # apply milvus patch
    patch -p1 < ../milvus_patches/${MILVUS_PATCH_NAME}.patch
    cd -
fi

# get host
OS=$(uname -s)
ARCH=$(arch)


# patch Makefile
if [[ "${OS}" == "Darwin" ]] ; then
    sed -i '' 's/-ldflags="/-ldflags="-s -w /' milvus/Makefile
    sed -i '' 's/-ldflags="-s -w -s -w /-ldflags="-s -w /' milvus/Makefile
else
    sed 's/-ldflags="/-ldflags="-s -w /' -i milvus/Makefile
    sed 's/-ldflags="-s -w -s -w /-ldflags="-s -w /' -i milvus/Makefile
fi


## functions for each os

function build_msys() {
    cd milvus
    bash scripts/install_deps_msys.sh
    source scripts/setenv.sh

    # this is needed when first install golang without restarting the shell
    export GOROOT=/mingw64/lib/go
    go version

    make -j $(nproc) milvus

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
        make -j $(nproc) milvus
        cd bin
        rm -fr lib*

        for x in $(ldd milvus | awk '{print $1}') ; do
            if [[ $x =~ libc.so.* ]] ; then
                :
            elif [[ $x =~ libdl.so.* ]] ; then
                :
            elif [[ $x =~ libm.so.* ]] ; then
                :
            elif [[ $x =~ librt.so.* ]] ; then
                :
            elif [[ $x =~ libpthread.so.* ]] ; then
                :
            elif test -f $x ; then
                :
            else
                echo $x
                for p in ../internal/core/output/lib ../internal/core/output/lib64 /lib64 /usr/lib64 /usr/local/lib64 /usr/local/lib /usr/lib64/boost169 ; do
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
        ## docker build -t matrixji/python-milvus-server-builder:latest ${docker_build_proxys} tools/build-env-manylinux2014
        mkdir -p tmp
        docker run -u $(id -u):$(id -g) -e HOME=/tmp -e BUILD_ALREADY_IN_DOCKER=YES --rm -ti ${docker_run_proxys} \
            -v$(pwd):/src \
            -v$(pwd)/tmp:/tmp \
            matrixji/python-milvus-server-builder:manylinux2004-1 bash -c "cd /src && bash run-prebuild.sh"
    fi
}

build_macosx_arm64() {
    cd milvus
    source scripts/setenv.sh
    export PKG_CONFIG_PATH=${PKG_CONFIG_PATH}:$(brew --prefix openssl)/lib/pkgconfig
    make -j $(sysctl -n hw.physicalcpu) milvus

    # resolve dependencies for milvus
    cd bin
    rm -fr lib*
    files=("milvus")
    while true ; do
        new_files=()
        for file in ${files[@]} ; do
            for line in $(otool -L $file | grep -v ${file}: | grep -v /usr/lib | grep -v /System/Library | awk '{print $1}') ; do
                filename=$(basename $line)
                if [[ -f ${filename} ]] ; then
                    continue
                fi
                find_in_build_dir=$(find ../cmake_build -name $filename)
                if [[ ! -z "$find_in_build_dir" ]] ; then
                    cp -frv ${find_in_build_dir} ${filename}
                    new_files+=( "${filename}" )
                    continue
                fi
                if [[ -f $line ]] ; then
                    cp -frv $line $filename
                    new_files+=( "${filename}" )
                    continue
                fi
            done
        done
        if [[ ${#new_files[@]} -eq 0 ]] ; then
            break
        fi
        for file in ${new_files[@]} ; do
            files+=( ${file} )
        done
    done
}



case $OS in
    Linux)
        build_linux_${ARCH}
        ;;
    MINGW*)
        build_msys
        ;;
    Darwin)
        build_macosx_${ARCH}
        ;;
    *)
        ;;
esac

