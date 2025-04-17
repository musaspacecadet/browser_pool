FROM alpine:3.20

# Ensure local Python is preferred over distribution Python
ENV PATH /usr/local/bin:$PATH

# Runtime dependencies
RUN set -eux; \
    apk add --no-cache \
        bash \
        ca-certificates \
        tzdata \
        ;

ENV GPG_KEY 7169605F62C751356D054A26A821E680E5FA6305
ENV PYTHON_VERSION 3.13.1
ENV PYTHON_SHA256 9cf9427bee9e2242e3877dd0f6b641c1853ca461f39d6503ce260a59c80bf0d9

RUN set -eux; \
    apk add --no-cache --virtual .build-deps \
        gnupg \
        tar \
        xz \
        bash \
        \
        bluez-dev \
        bzip2-dev \
        dpkg-dev dpkg \
        findutils \
        gcc \
        gdbm-dev \
        libc-dev \
        libffi-dev \
        libnsl-dev \
        libtirpc-dev \
        linux-headers \
        make \
        ncurses-dev \
        openssl-dev \
        pax-utils \
        readline-dev \
        sqlite-dev \
        tcl-dev \
        tk \
        tk-dev \
        util-linux-dev \
        xz-dev \
        zlib-dev \
    ; \
    \
    wget -O python.tar.xz "https://www.python.org/ftp/python/${PYTHON_VERSION%%[a-z]*}/Python-$PYTHON_VERSION.tar.xz"; \
    echo "$PYTHON_SHA256 *python.tar.xz" | sha256sum -c -; \
    wget -O python.tar.xz.asc "https://www.python.org/ftp/python/${PYTHON_VERSION%%[a-z]*}/Python-$PYTHON_VERSION.tar.xz.asc"; \
    GNUPGHOME="$(mktemp -d)"; export GNUPGHOME; \
    gpg --batch --keyserver hkps://keys.openpgp.org --recv-keys "$GPG_KEY"; \
    gpg --batch --verify python.tar.xz.asc python.tar.xz; \
    gpgconf --kill all; \
    rm -rf "$GNUPGHOME" python.tar.xz.asc; \
    mkdir -p /usr/src/python; \
    tar --extract --directory /usr/src/python --strip-components=1 --file python.tar.xz; \
    rm python.tar.xz; \
    \
    cd /usr/src/python; \
    gnuArch="$(dpkg-architecture --query DEB_BUILD_GNU_TYPE)"; \
    ./configure \
        --build="$gnuArch" \
        --enable-loadable-sqlite-extensions \
        --enable-option-checking=fatal \
        --enable-shared \
        --with-lto \
        --with-ensurepip \
        --disable-gil \
    ; \
    nproc="$(nproc)"; \
    EXTRA_CFLAGS="-DTHREAD_STACK_SIZE=0x100000"; \
    LDFLAGS="${LDFLAGS:--Wl},--strip-all"; \
    make -j "$nproc" \
        "EXTRA_CFLAGS=${EXTRA_CFLAGS:-}" \
        "LDFLAGS=${LDFLAGS:-}" \
    ; \
    make -j "$nproc" \
        "EXTRA_CFLAGS=${EXTRA_CFLAGS:-}" \
        "LDFLAGS=${LDFLAGS:--Wl},-rpath='\$\$ORIGIN/../lib'" \
        python \
    ; \
    make install; \
    \
    cd /; \
    rm -rf /usr/src/python; \
    \
    find /usr/local -depth \
        \( \
            \( -type d -a \( -name test -o -name tests -o -name idle_test \) \) \
            -o \( -type f -a \( -name '*.pyc' -o -name '*.pyo' -o -name 'libpython*.a' \) \) \
        \) -exec rm -rf '{}' + \
    ; \
    \
    find /usr/local -type f -executable -not \( -name '*tkinter*' \) -exec scanelf --needed --nobanner --format '%n#p' '{}' ';' \
        | tr ',' '\n' \
        | sort -u \
        | awk 'system("[ -e /usr/local/lib/" $1 " ]") == 0 { next } { print "so:" $1 }' \
        | xargs -rt apk add --no-network --virtual .python-rundeps \
    ; \
    apk del --no-network .build-deps; \
    \
    export PYTHONDONTWRITEBYTECODE=1; \
    python3 --version; \
    pip3 --version

# Create symbolic links for commonly used binaries
RUN set -eux; \
    for src in idle3 pip3 pydoc3 python3 python3-config; do \
        dst="$(echo "$src" | tr -d 3)"; \
        [ -s "/usr/local/bin/$src" ]; \
        [ ! -e "/usr/local/bin/$dst" ]; \
        ln -svT "$src" "/usr/local/bin/$dst"; \
    done

# Copy the rest of the application
COPY . /app

# Set working directory
WORKDIR /app

# Install dependencies
# A target directory is required since the latest versions of Alpine have implemented PEP 668 
# which prevents pip from installing packages system-wide.
RUN python3 -m pip install --target /app -r requirements.txt

# Install AWS Lambda Runtime Interface Client
RUN python3 -m pip install --target /app awslambdaric

# Define the entrypoint
ENTRYPOINT ["python3", "-m", "awslambdaric"]

# Set the handler to be used by the Lambda runtime
CMD ["main.handler"]
