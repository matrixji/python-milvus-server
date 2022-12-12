#!/bin/bash

set -e

yum -y update && yum -y install wget

if ! /usr/local/go/bin/go version 2>/dev/null | grep -wq go1.18.9 ; then
    rm -fr /usr/local/go && \
    cd /usr/local && \
    (wget https://studygolang.com/dl/golang/go1.18.9.linux-amd64.tar.gz || \
     wget https://go.dev/dl/go1.18.9.linux-amd64.tar.gz) && \
    tar xvf go1.18.9.linux-amd64.tar.gz && \
    rm -fr go1.18.9.linux-amd64.tar.gz
fi

yum -y install make lcov libtool m4 autoconf automake ccache \
    openssl-devel zlib-devel libzstd-devel libcurl-devel \
    libuuid-devel pulseaudio-libs-devel \
    boost169-devel lapack-devel

export PATH=${PATH}:/usr/local/go/bin
export BOOST_INCLUDEDIR=/usr/include/boost169
export BOOST_LIBRARYDIR=/usr/lib64/boost169

# patch for find boost easy
if ! test -L /usr/include/boost ; then
    ln -s /usr/include/boost169/boost /usr/include/boost
fi

# TBB
if ! test -f /usr/local/lib/libtbb.so ; then
    git clone https://github.com/wjakob/tbb.git && \
        cd tbb/build && \
        cmake .. && make -j && \
        make install && \
        cd ../../ && rm -rf tbb/
fi

# cleanup cache
yum clean all
rm -fr ~/.cache
