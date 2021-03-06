#!/usr/bin/env python
# -*- coding: utf-8 -*-
# <bitbar.title>Meta Package Manager</bitbar.title>
# <bitbar.version>v1.11.0</bitbar.version>
# <bitbar.author>Kevin Deldycke</bitbar.author>
# <bitbar.author.github>kdeldycke</bitbar.author.github>
# <bitbar.desc>List package updates from several managers.</bitbar.desc>
# <bitbar.dependencies>python</bitbar.dependencies>
# <bitbar.image>https://i.imgur.com/CiQpQ42.png</bitbar.image>
# <bitbar.abouturl>https://github.com/kdeldycke/meta-package-manager</bitbar.abouturl>

"""
Default update cycle is set to 7 hours so we have a chance to get user's
attention once a day. Higher frequency might ruin the system as all checks are
quite resource intensive, and Homebrew might hit GitHub's API calls quota.
"""

from __future__ import print_function, unicode_literals

import json
import os
import re
import sys
from operator import methodcaller
from subprocess import PIPE, Popen, call

# macOS does not put /usr/local/bin or /opt/local/bin in the PATH for GUI apps.
# For some package managers this is a problem. Additioanlly Homebrew and
# Macports are using different pathes.  So, to make sure we can always get to
# the necessary binaries, we overload the path.  Current preference order would
# equate to Homebrew, Macports, then System.
os.environ['PATH'] = ':'.join(['/usr/local/bin',
                               '/usr/local/sbin',
                               '/opt/local/bin',
                               '/opt/local/sbin',
                               os.environ.get('PATH', '')])


class PackageManager(object):
    """ Generic class for a package manager. """

    cli = None

    def __init__(self):
        # List all available updates and their versions.
        self.updates = []
        self.error = None

    @property
    def name(self):
        """ Return package manager's common name. Defaults based on class name.
        """
        return self.__class__.__name__

    @property
    def active(self):
        """ Is the package manager available on the system?

        Returns True is the main CLI exists and is executable.
        """
        return os.path.isfile(self.cli) and os.access(self.cli, os.X_OK)

    def run(self, *args):
        """ Run a shell command, return the output and keep error message.
        """
        self.error = None
        process = Popen(
            args, stdout=PIPE, stderr=PIPE, universal_newlines=True)
        output, error = process.communicate()
        if process.returncode != 0 and error:
            self.error = error.decode('utf-8')
        return output.decode('utf-8')

    def sync(self):
        """ Fetch latest versions of installed packages.

        Returns a list of dict with package name, current installed version and
        latest upgradeable version.
        """
        raise NotImplementedError

    @staticmethod
    def bitbar_cli_format(full_cli):
        """ Format a bash-runnable full-CLI with parameters into bitbar schema.
        """
        cmd, params = full_cli.strip().split(' ', 1)
        bitbar_cli = "bash={}".format(cmd)
        for index, param in enumerate(params.split(' ')):
            bitbar_cli += " param{}={}".format(index + 1, param)
        return bitbar_cli

    def update_cli(self, package_name):
        """ Return a bitbar-compatible full-CLI to update a package. """
        raise NotImplementedError

    def update_all_cli(self):
        """ Return a bitbar-compatible full-CLI to update all packages. """
        raise NotImplementedError

    def _update_all_cmd(self):
        return '{} upgrade {}'.format(sys.argv[0], self.__class__.__name__)

    def update_all_cmd(self):
        pass


class Homebrew(PackageManager):

    cli = '/usr/local/bin/brew'

    def sync(self):
        """ Fetch latest Homebrew formulas.

        Sample of brew output:

            $ brew outdated --json=v1
            [
              {
                "name": "cassandra",
                "installed_versions": [
                  "3.5"
                ],
                "current_version": "3.7"
              },
              {
                "name": "vim",
                "installed_versions": [
                  "7.4.1967"
                ],
                "current_version": "7.4.1993"
              },
              {
                "name": "youtube-dl",
                "installed_versions": [
                  "2016.07.06"
                ],
                "current_version": "2016.07.09.1"
              }
            ]
        """
        self.run(self.cli, 'update')

        # List available updates.
        output = self.run(self.cli, 'outdated', '--json=v1')
        if not output:
            return

        for pkg_info in json.loads(output):
            self.updates.append({
                'name': pkg_info['name'],
                # Only keeps the highest installed version.
                'installed_version': max(pkg_info['installed_versions']),
                'latest_version': pkg_info['current_version']})

    def update_cli(self, package_name=None):
        cmd = "{} upgrade --cleanup".format(self.cli)
        if package_name:
            cmd += " {}".format(package_name)
        return self.bitbar_cli_format(cmd)

    def update_all_cli(self):
        return self.update_cli()


class HomebrewCask(Homebrew):

    @property
    def active(self):
        """ Cask depends on vanilla Homebrew. """
        if super(HomebrewCask, self).active:
            cask = Popen([self.cli, 'cask'], stdout=PIPE, stderr=PIPE)
            cask.communicate()
            return cask.returncode == 0
        return False

    def sync(self):
        """ Fetch latest formulas and their metadata.

        Sample of brew cask output:

            $ brew cask list --versions
            aerial 1.2beta5
            android-file-transfer latest
            audacity 2.1.2
            bitbar 1.9.2
            firefox 49.0.1
            flux 37.7
            gimp 2.8.18-x86_64
            java 1.8.0_112-b16

            $ brew cask info aerial
            aerial: 1.2beta5
            https://github.com/JohnCoates/Aerial
            /usr/local/Caskroom/aerial/1.2beta5 (18 files, 6.6M)
            From: https://github.com/caskroom/homebrew-cask/blob/master/Casks/aerial.rb
            ==> Name
            Aerial Screensaver
            ==> Artifacts
            Aerial.saver (screen_saver)

            $ brew cask info firefox
            firefox: 50.0.1
            https://www.mozilla.org/firefox/
            /usr/local/Caskroom/firefox/49.0.1 (107 files, 185.3M)
            From: https://github.com/caskroom/homebrew-cask/blob/master/Casks/firefox.rb
            ==> Name
            Mozilla Firefox
            ==> Artifacts
            Firefox.app (app)

            $ brew cask info prey
            prey: 1.6.3
            https://preyproject.com/
            Not installed
            From: https://github.com/caskroom/homebrew-cask/blob/master/Casks/prey.rb
            ==> Name
            Prey
            ==> Artifacts
            prey-mac-1.6.3-x86.pkg (pkg)
            ==> Caveats
            Prey requires your API key, found in the bottom-left corner of
            the Prey web account Settings page, to complete installation.
            The API key may be set as an environment variable as follows:

              API_KEY="abcdef123456" brew cask install prey

            $ brew cask info ubersicht
            ubersicht: 1.0.44
            http://tracesof.net/uebersicht/
            Not installed
            From: https://github.com/caskroom/homebrew-cask/blob/master/Casks/ubersicht.rb
            ==> Name
            Übersicht
            ==> Artifacts
            Übersicht.app (app)
        """
        # `brew cask update` is just an alias to `brew update`. Perform the
        # action anyway to make it future proof.
        self.run(self.cli, 'cask', 'update')

        # List installed packages.
        output = self.run(self.cli, 'cask', 'list', '--versions')

        # Inspect package one by one as `brew cask list` is not reliable. See:
        # https://github.com/caskroom/homebrew-cask/blob/master/doc
        # /reporting_bugs/brew_cask_list_shows_wrong_information.md
        for installed_pkg in output.strip().split('\n'):
            if not installed_pkg:
                continue
            infos = installed_pkg.split(' ', 1)
            name = infos[0]

            # Use heuristics to guess installed version.
            versions = infos[1] if len(infos) > 1 else ''
            versions = sorted([
                v.strip() for v in versions.split(',') if v.strip()])
            if len(versions) > 1 and 'latest' in versions:
                versions.remove('latest')
            version = versions[-1] if versions else '?'

            # TODO: Support packages removed from repository (reported with a
            # `(!)` flag). See: https://github.com/caskroom/homebrew-cask/blob
            # /master/doc/reporting_bugs
            # /uninstall_wrongly_reports_cask_as_not_installed.md

            # Inspect the package closer to evaluate its state.
            output = self.run(self.cli, 'cask', 'info', name)

            latest_version = output.split('\n')[0].split(' ')[1]

            # Skip already installed packages.
            if version == latest_version:
                continue

            self.updates.append({
                'name': name,
                'installed_version': version,
                'latest_version': latest_version})

    def update_cli(self, package_name):
        """ Install a package.

        TODO: wait for https://github.com/caskroom/homebrew-cask/issues/22647
        so we can force a cleanup in one go, as we do above with vanilla
        Homebrew.
        """
        return self.bitbar_cli_format(
            "{} cask reinstall {}".format(self.cli, package_name))

    def update_all_cli(self):
        """ Cask has no way to update all outdated packages.

        See: https://github.com/caskroom/homebrew-cask/issues/4678
        """
        return self.bitbar_cli_format(self._update_all_cmd())

    def update_all_cmd(self):
        self.sync()
        for package in self.updates:
            call("{} cask reinstall {}".format(self.cli, package['name']),
                 shell=True)


class Pip(PackageManager):

    def sync(self):
        """ List outdated packages and their metadata.

        Sample of pip output:

            $ pip list --outdated
            ccm (2.1.8, /Users/kdeldycke/ccm) - Latest: 2.1.11 [sdist]
            coverage (4.0.3) - Latest: 4.1 [wheel]
            IMAPClient (0.13) - Latest: 1.0.1 [wheel]
            Logbook (0.10.1) - Latest: 1.0.0 [sdist]
            mccabe (0.4.0) - Latest: 0.5.0 [wheel]
            mercurial (3.8.3) - Latest: 3.8.4 [sdist]
            pylint (1.5.6) - Latest: 1.6.1 [wheel]
        """
        output = self.run(self.cli, 'list', '--outdated').strip()
        if not output:
            return

        regexp = re.compile(r'(\S+) \((.*)\) - Latest: (\S+)')
        for outdated_pkg in output.split('\n'):
            if not outdated_pkg:
                continue

            name, installed_info, latest_version = regexp.match(
                outdated_pkg).groups()

            # Extract current non-standard location if found.
            installed_info = installed_info.split(',', 1)
            version = installed_info[0]
            special_location = " ({})".format(
                installed_info[1].strip()) if len(installed_info) > 1 else ''

            self.updates.append({
                'name': name + special_location,
                'installed_version': version,
                'latest_version': latest_version})

    def update_cli(self, package_name):
        return self.bitbar_cli_format(
            "{} install --upgrade {}".format(self.cli, package_name))

    def update_all_cli(self):
        """ Produce a long CLI with all upgradeable package names.

        This work around the lack of proper full upgrade command in Pip.
        See: https://github.com/pypa/pip/issues/59
        """
        return self.bitbar_cli_format(self._update_all_cmd())

    def update_all_cmd(self):
        self.sync()
        for package in self.updates:
            call("{} install -U {}".format(self.cli, package["name"]),
                 shell=True)


class Pip2(Pip):

    cli = '/usr/local/bin/pip2'

    @property
    def name(self):
        return "Python 2 pip"


class Pip3(Pip):

    cli = '/usr/local/bin/pip3'

    @property
    def name(self):
        return "Python 3 pip"


class NPM(PackageManager):

    cli = '/usr/local/bin/npm'

    @property
    def name(self):
        return "npm"

    def sync(self):
        """
        Sample of npm output:

            $ npm -g --progress=false --json outdated
            {
              "my-linked-package": {
                "current": "0.0.0-development",
                "wanted": "linked",
                "latest": "linked",
                "location": "/Users/..."
              },
              "npm": {
                "current": "3.10.3",
                "wanted": "3.10.5",
                "latest": "3.10.5",
                "location": "/Users/..."
              }
            }
        """
        output = self.run(
            self.cli, '-g', '--progress=false', '--json', 'outdated')
        if not output:
            return

        for package, values in json.loads(output).iteritems():
            if values['wanted'] == 'linked':
                continue
            self.updates.append({
                'name': package,
                'installed_version':
                    values['current'] if 'current' in values else '',
                'latest_version': values['latest']
            })

    def update_cli(self, package_name=None):
        cmd = "{} -g --progress=false update".format(self.cli)
        if package_name:
            cmd += " {}".format(package_name)
        return self.bitbar_cli_format(cmd)

    def update_all_cli(self):
        return self.update_cli()


class APM(PackageManager):

    cli = '/usr/local/bin/apm'

    @property
    def name(self):
        return "apm"

    def sync(self):
        output = self.run(self.cli, 'outdated', '--compatible', '--json')
        if not output:
            return

        for package in json.loads(output):
            self.updates.append({
                'name': package['name'],
                'installed_version': package['version'],
                'latest_version': package['latestVersion']
            })

    def update_cli(self, package_name=None):
        cmd = "{} update --no-confirm".format(self.cli)
        if package_name:
            cmd += " {}".format(package_name)
        return self.bitbar_cli_format(cmd)

    def update_all_cli(self):
        return self.update_cli()


class Gems(PackageManager):
    HOMEBREW_PATH = '/usr/local/bin/gem'
    SYSTEM_PATH = '/usr/bin/gem'

    def __init__(self):
        super(Gems, self).__init__()

        self.system = True
        if os.path.exists(Gems.HOMEBREW_PATH):
            self.system = False
            self._cli = Gems.HOMEBREW_PATH
        else:
            self._cli = Gems.SYSTEM_PATH

    @property
    def cli(self):
        return self._cli

    @property
    def name(self):
        return "Ruby Gems"

    def sync(self):
        """
        Sample of gem output:

            $ gem outdated
            did_you_mean (1.0.0 < 1.0.2)
            io-console (0.4.5 < 0.4.6)
            json (1.8.3 < 2.0.1)
            minitest (5.8.3 < 5.9.0)
            power_assert (0.2.6 < 0.3.0)
            psych (2.0.17 < 2.1.0)
        """
        # outdated does not require sudo privileges on homebrew or system
        output = self.run(self.cli, 'outdated')

        regexp = re.compile(r'(\S+) \((\S+) < (\S+)\)')
        for package in output.split('\n'):
            if not package:
                continue
            name, current_version, latest_version = regexp.match(
                package).groups()
            self.updates.append({
                'name': name,
                'installed_version': current_version,
                'latest_version': latest_version
            })

    def update_cli(self, package_name=None):
        # installs require sudo on system ruby
        cmd = "{}{} update".format(
            '/usr/bin/sudo ' if self.system else '',
            self.cli)
        if package_name:
            cmd += " {}".format(package_name)
        return self.bitbar_cli_format(cmd)

    def update_all_cli(self):
        return self.update_cli()


class MAS(PackageManager):

    cli = '/usr/local/bin/mas'

    def __init__(self):
        super(MAS, self).__init__()
        self.map = {}

    @property
    def name(self):
        return "Mac AppStore"

    def sync(self):
        output = self.run(self.cli, 'outdated')
        if not output:
            return

        regexp = re.compile(r'(\d+) (.*) \((\S+) -> (\S+)\)$')
        for application in output.split('\n'):
            if not application:
                continue
            _id, name, installed_version, latest_version = regexp.match(
                application).groups()
            self.map[name] = _id
            self.updates.append({
                'name': name,
                'latest_version': latest_version,
                # Normalize unknown version. See: https://github.com/mas-cli
                # /mas/commit/1859eaedf49f6a1ebefe8c8d71ec653732674341
                'installed_version': (
                    installed_version if installed_version != 'unknown'
                    else '')})

    def update_cli(self, package_name):
        if package_name not in self.map:
            return None
        cmd = "{} install {}".format(self.cli, self.map[package_name])
        return self.bitbar_cli_format(cmd)

    def update_all_cli(self):
        cmd = "{} upgrade".format(self.cli)
        return self.bitbar_cli_format(cmd)


def print_menu():
    """ Print menu structure using BitBar's plugin API.

    See: https://github.com/matryer/bitbar#plugin-api
    """
    # Instantiate all available package manager.
    managers = [k() for k in [
        Homebrew, HomebrewCask, Pip2, Pip3, APM, NPM, Gems, MAS]]

    # Filters-out inactive managers.
    managers = [m for m in managers if m.active]

    # Sync all managers.
    map(methodcaller('sync'), managers)

    # Print menu bar icon with number of available updates.
    total_updates = sum([len(m.updates) for m in managers])
    errors = [True for m in managers if m.error]
    print(("↑{} {}| dropdown=false".format(
        total_updates,
        "⚠️{}".format(len(errors)) if errors else ""
    )).encode('utf-8'))

    # Print a full detailed section for each manager.
    for manager in managers:
        print("---")

        if manager.error:
            for line in manager.error.strip().split("\n"):
                print("{} | color=red".format(line))

        print("{} {} package{}".format(
            len(manager.updates),
            manager.name,
            's' if len(manager.updates) != 1 else ''))

        if manager.update_all_cli() and manager.updates:
            print("Upgrade all | {} terminal=false refresh=true".format(
                manager.update_all_cli()))

        for pkg_info in manager.updates:
            print((
                "{name} {installed_version} → {latest_version} | "
                "{cli} terminal=false refresh=true".format(
                    cli=manager.update_cli(pkg_info['name']),
                    **pkg_info)).encode('utf-8'))

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs='?', default='menu')
    parser.add_argument("options", nargs='*')

    args = parser.parse_args()

    if args.command == 'upgrade':
        try:
            # Instantiate class from global definitions
            cl = globals()[args.options[0]]()
            cl.update_all_cmd()
        except:
            # Do nothing if we can't load the class
            pass
    else:
        print_menu()
