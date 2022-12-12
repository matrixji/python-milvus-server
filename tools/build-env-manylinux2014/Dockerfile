# centos 7
FROM quay.io/pypa/manylinux2014_x86_64

COPY install_deps.sh /tmp

RUN bash /tmp/install_deps.sh

ENV PATH=${PATH}:/usr/local/go/bin
ENV BOOST_INCLUDEDIR=/usr/include/boost169
ENV BOOST_LIBRARYDIR=/usr/lib64/boost169

