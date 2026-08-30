# shellcheck shell=bash
#
# ShellCheck: this file is sourced by BOTH bash and zsh, so shellcheck (which
# parses it as bash) necessarily misreads the zsh half. Each disable below is
# specific and permanent, not a way around the gate:
# shellcheck disable=SC2059  # __git_ps1 fallback: the format string IS the argument
# shellcheck disable=SC2154  # debian_chroot is exported by Debian's /etc/bash.bashrc
# shellcheck disable=SC2034  # SAVEHIST/PROMPT are read by zsh, invisible to shellcheck
# shellcheck disable=SC2016  # zsh PROMPT relies on PROMPT_SUBST: it must NOT expand here
# Git-aware prompt and tab completion for the defendable-science devcontainer.
#
# Sourced from ~/.bashrc and ~/.zshrc by install-shell-prompt.sh. Replaces the
# stock "user@host:cwd$" prompt with "cwd (branch)$" -- the user and host are
# noise inside a container, the branch is not -- and wires up completion for
# the CLIs that do not ship a completion file (gh, uv), fzf key bindings,
# EDITOR/PAGER, and history defaults. The packages behind this are installed by
# shared/install_common_tools.sh.
#
# A virtualenv prefix (e.g. "(defendable-science) ") is still prepended by the activate
# script via VIRTUAL_ENV_PROMPT / PS1 rewriting, so it survives this.

# The image has no editor and no pager alternative until
# install_common_tools.sh runs; git then resolves core.editor -> EDITOR ->
# /usr/bin/editor. Set these only when the caller has not.
if [ -z "${EDITOR:-}" ] && command -v vim >/dev/null 2>&1; then
    EDITOR=vim
    export EDITOR
fi
[ -z "${VISUAL:-}" ] && [ -n "${EDITOR:-}" ] && export VISUAL="$EDITOR"
# -F: skip the pager for output that fits one screen. -R: keep git/gh colors.
# -X: leave the output on screen after quitting. Matches git's own default.
[ -z "${LESS:-}" ] && export LESS="-FRX"

# The stock rc keeps 1000 lines with no timestamps, which is not much history
# for a long-lived container.
HISTSIZE=100000
HISTFILESIZE=200000
HISTCONTROL=ignoreboth:erasedups
HISTTIMEFORMAT='%F %T '
export HISTSIZE HISTFILESIZE HISTCONTROL HISTTIMEFORMAT

# Cache dir for generated completion scripts (gh/uv emit them on stdout;
# regenerating on every shell start would cost a subprocess each).
_defsci_comp_cache="${XDG_CACHE_HOME:-$HOME/.cache}/defsci-shell"

# _defsci_completion <tool> <shell> <arg>...
# Cache `<tool> <arg>...` output once, then source it.
_defsci_completion() {
    local tool=$1 shell=$2
    shift 2
    command -v "$tool" >/dev/null 2>&1 || return 0
    local cache="$_defsci_comp_cache/$tool.$shell"
    if [ ! -s "$cache" ]; then
        mkdir -p "$_defsci_comp_cache"
        "$tool" "$@" > "$cache" 2>/dev/null || { rm -f "$cache"; return 0; }
    fi
    # shellcheck disable=SC1090
    . "$cache"
}

if [ -n "${BASH_VERSION:-}" ]; then

    # The stock ~/.bashrc sources the bash-completion loader when present, but
    # only some images ship it; load it here too so this file works standalone.
    # (install_common_tools.sh apt-installs the package.)
    if ! declare -F _completion_loader >/dev/null 2>&1 && ! shopt -oq posix; then
        for _defsci_bc in \
            /usr/share/bash-completion/bash_completion \
            /etc/bash_completion
        do
            # shellcheck disable=SC1090
            [ -r "$_defsci_bc" ] && . "$_defsci_bc" && break
        done
        unset _defsci_bc
    fi

    _defsci_completion gh bash completion -s bash
    _defsci_completion uv bash generate-shell-completion bash

    # Debian ships __git_ps1 in git-sh-prompt, but the container has no
    # bash-completion loader to source it, so do it ourselves.
    if ! declare -F __git_ps1 >/dev/null 2>&1; then
        for _defsci_gitprompt in \
            /usr/lib/git-core/git-sh-prompt \
            /usr/share/git-core/contrib/completion/git-prompt.sh \
            /etc/bash_completion.d/git-prompt
        do
            # shellcheck disable=SC1090
            [ -r "$_defsci_gitprompt" ] && . "$_defsci_gitprompt" && break
        done
        unset _defsci_gitprompt
    fi

    if ! declare -F __git_ps1 >/dev/null 2>&1; then
        # Fallback: no git-sh-prompt available in this image.
        __git_ps1() {
            local branch
            branch=$(git symbolic-ref --short -q HEAD 2>/dev/null) ||
                branch=$(git rev-parse --short HEAD 2>/dev/null) || return 0
            printf "${1:- (%s)}" "$branch"
        }
    fi

    GIT_PS1_SHOWDIRTYSTATE=1      # * unstaged, + staged
    GIT_PS1_SHOWSTASHSTATE=1      # $ stashed
    GIT_PS1_SHOWUNTRACKEDFILES=1  # % untracked
    GIT_PS1_SHOWUPSTREAM=auto     # </>/= vs upstream
    export GIT_PS1_SHOWDIRTYSTATE GIT_PS1_SHOWSTASHSTATE \
        GIT_PS1_SHOWUNTRACKEDFILES GIT_PS1_SHOWUPSTREAM

    PS1='${debian_chroot:+($debian_chroot)}\[\033[01;34m\]\w\[\033[00m\]\[\033[01;33m\]$(__git_ps1 " (%s)")\[\033[00m\]\$ '

    case "$TERM" in
        xterm* | rxvt* | screen* | tmux*)
            PS1="\[\e]0;\w\a\]$PS1"
            ;;
    esac

    shopt -s histappend globstar

    # Readline: Up/Down search history by what is already typed rather than
    # walking it blindly; completion ignores case and lists on first ambiguity.
    if [[ $- == *i* ]]; then
        bind '"\e[A": history-search-backward' 2>/dev/null
        bind '"\e[B": history-search-forward' 2>/dev/null
        bind 'set completion-ignore-case on' 2>/dev/null
        bind 'set show-all-if-ambiguous on' 2>/dev/null
        bind 'set colored-stats on' 2>/dev/null
    fi

    # fzf: Ctrl-R fuzzy history, Ctrl-T file picker, Alt-C cd. The Debian
    # package ships the bindings as an example file rather than sourcing them.
    # Must come after the bind calls above -- fzf rebinds Ctrl-R.
    # shellcheck disable=SC1091
    [ -r /usr/share/doc/fzf/examples/key-bindings.bash ] &&
        . /usr/share/doc/fzf/examples/key-bindings.bash

elif [ -n "${ZSH_VERSION:-}" ]; then

    # oh-my-zsh runs compinit itself; only do it when nothing else has.
    if ! whence -w compdef >/dev/null 2>&1; then
        autoload -Uz compinit && compinit -u
    fi
    zstyle ':completion:*' menu select
    zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'

    _defsci_completion gh zsh completion -s zsh
    _defsci_completion uv zsh generate-shell-completion zsh

    setopt APPEND_HISTORY SHARE_HISTORY HIST_IGNORE_ALL_DUPS \
        HIST_IGNORE_SPACE EXTENDED_GLOB
    HISTFILE="${HISTFILE:-$HOME/.zsh_history}"
    SAVEHIST=$HISTFILESIZE

    # Same prefix-search-on-arrow behaviour as the bash half.
    autoload -Uz up-line-or-beginning-search down-line-or-beginning-search
    zle -N up-line-or-beginning-search
    zle -N down-line-or-beginning-search
    bindkey '^[[A' up-line-or-beginning-search
    bindkey '^[[B' down-line-or-beginning-search

    for _defsci_fzf in /usr/share/doc/fzf/examples/completion.zsh \
        /usr/share/doc/fzf/examples/key-bindings.zsh
    do
        # shellcheck disable=SC1090
        [ -r "$_defsci_fzf" ] && . "$_defsci_fzf"
    done
    unset _defsci_fzf

    autoload -Uz vcs_info
    zstyle ':vcs_info:*' enable git
    zstyle ':vcs_info:git:*' check-for-changes true
    zstyle ':vcs_info:git:*' unstagedstr '*'
    zstyle ':vcs_info:git:*' stagedstr '+'
    zstyle ':vcs_info:git:*' formats       ' (%b%u%c)'
    zstyle ':vcs_info:git:*' actionformats ' (%b|%a%u%c)'

    _defsci_precmd() { vcs_info; }
    autoload -Uz add-zsh-hook
    add-zsh-hook precmd _defsci_precmd

    setopt PROMPT_SUBST
    PROMPT='%F{blue}%~%f%F{yellow}${vcs_info_msg_0_}%f%# '

fi

# Always leave a zero exit status. The last statement in the bash branch above
# is a short-circuit `[ -r ... ] && . ...` whose test fails whenever fzf's
# key-bindings file is absent -- which would make `. shell-prompt.sh` return 1
# and abort any caller running under `set -e`. (Carried over from mononet,
# which has the same latent issue.)
:
