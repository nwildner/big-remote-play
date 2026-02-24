# Spec file for big-remote-play
# Adapted from Arch Linux PKGBUILD by Nicolas Wildner(nwildner) <nicolasgaucho@gmail.com>

Name:           big-remote-play
Version:        %(date +%y.%m.%d)
Release:        %(date +%H%M)%{?dist}
Summary:        Integrated remote cooperative gaming system

License:        GPLv3
URL:            https://github.com/nwildner/%{name}
Source0:        %{url}/archive/HEAD.tar.gz#/%{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3
Requires:       gtk4
Requires:       libadwaita
Requires:       python3-gobject
Requires:       python3-cairo
Requires:       avahi
Requires:       curl
Requires:       iproute
Requires:       Sunshine
Requires:       moonlight-qt
Requires:       icu
Requires:       podman-docker
Requires:       podman-compose
Requires:       jq
Requires:       miniupnpc

%description
Integrated remote cooperative gaming system.
This package provides the necessary components and scripts to enable
remote cooperative gaming, leveraging tools like Sunshine and Moonlight.

%prep
%autosetup -n %{name}

%build

%install
if [ -d "%{name}/%{name}" ]; then
    INTERNAL_DIR="%{name}/%{name}"
else
    INTERNAL_DIR="%{name}"
fi

if [ -d "${INTERNAL_DIR}/usr" ]; then
    cp -a "${INTERNAL_DIR}/usr" "%{buildroot}/"
fi

if [ -d "${INTERNAL_DIR}/etc" ]; then
    cp -a "${INTERNAL_DIR}/etc" "%{buildroot}/"
fi

if [ -d "${INTERNAL_DIR}/opt" ]; then
    cp -a "${INTERNAL_DIR}/opt" "%{buildroot}/"
fi

%files
%{_prefix}/*
%config(noreplace) /etc/*
/opt/*

%changelog
# Initial RPM release - adapted from Arch PKGBUILD.
* $(date +"%a %b %d %Y") Nicolas Wildner <nicolasgaucho@gmail.com> - %{version}-%{release}
- Initial package for Fedora, converted from Arch Linux PKGBUILD.
