#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later

themes.help() {
    cat <<EOF
themes.:
  all       : test & build all themes
  simple    : test & build simple theme
  suckless  : test & build suckless theme
  lint      : lint JS & CSS (LESS) files
  fix       : fix JS & CSS (LESS) files
  test      : test all themes
EOF
}

themes.all() {
    (
        set -e
        vite.simple.build
        vite.suckless.build
    )
    dump_return $?
}

themes.simple() {
    (
        set -e
        build_msg SIMPLE "theme: run build (simple)"
        vite.simple.build
    )
    dump_return $?
}

themes.suckless() {
    (
        set -e
        build_msg SUCKLESS "theme: run build (suckless)"
        vite.suckless.build
    )
    dump_return $?
}

themes.simple.analyze() {
    (
        set -e
        build_msg SIMPLE "theme: run analyze (simple)"
        vite.simple.analyze
    )
    dump_return $?
}

themes.fix() {
    (
        set -e
        build_msg SIMPLE "theme: fix (all themes)"
        vite.simple.fix
    )
    dump_return $?
}

themes.lint() {
    (
        set -e
        build_msg SIMPLE "theme: lint (all themes)"
        vite.simple.lint
        node.env
        npm --prefix client/suckless run lint
    )
    dump_return $?
}

themes.test() {
    (
        set -e
        # we run a build to test (in CI)
        build_msg THEMES "theme: run build (to test)"
        themes.all
    )
    dump_return $?
}
