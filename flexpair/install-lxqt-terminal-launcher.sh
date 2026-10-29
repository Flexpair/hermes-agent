#!/usr/bin/env bash
# Install a user-local LXQt launcher for the Flexpair Hermes CLI checkout.
set -euo pipefail

fail() {
  printf 'hermes launcher: %s\n' "$1" >&2
  exit 1
}

os_name=$(uname -s) || fail 'could not detect the operating system'
if [[ "$os_name" != Linux ]]; then
  printf 'hermes launcher: non-Linux platform (%s); skipping\n' "$os_name" >&2
  exit 0
fi

if (( EUID == 0 )); then
  fail 'refusing to install as root; run this helper as the desktop user'
fi

user_id=$(id -u) || fail 'could not determine the current user'
script_dir=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) \
  || fail 'could not resolve the helper directory'
repo_root=$(CDPATH='' cd -- "$script_dir/.." && pwd -P) \
  || fail 'could not resolve the Hermes checkout'
source_icon="$repo_root/apps/desktop/assets/icon.png"

if [[ -L "$source_icon" || ! -f "$source_icon" || ! -s "$source_icon" ]]; then
  fail "repo-local icon is missing, empty, or not a regular file: $source_icon"
fi
if ! png_header=$(od -An -tx1 -N24 -- "$source_icon" | tr -d '[:space:]'); then
  fail "could not read repo-local icon: $source_icon"
fi
if [[ ${#png_header} -ne 48 || "${png_header:0:32}" != 89504e470d0a1a0a0000000d49484452 \
  || "${png_header:32:8}" == 00000000 || "${png_header:40:8}" == 00000000 ]]; then
  fail "repo-local icon is not a valid PNG header: $source_icon"
fi

if [[ -z "${HOME:-}" || "$HOME" != /* || ! -d "$HOME" ]]; then
  fail 'HOME must name an existing absolute user directory'
fi
if [[ "$HOME" =~ [[:cntrl:]] ]]; then
  fail 'HOME contains a control character'
fi
# Preserve trailing newlines in the resolved path so validation can reject them.
real_home=$(CDPATH='' cd -P -- "$HOME" && printf '%sX' "$PWD") || fail 'could not resolve HOME'
real_home=${real_home%X}
if [[ "$real_home" =~ [[:cntrl:]] ]]; then
  fail 'resolved HOME contains a control character'
fi
home_owner=$(stat -c '%u' -- "$real_home") || fail 'could not inspect HOME ownership'
if [[ "$home_owner" != "$user_id" ]]; then
  fail 'HOME is not owned by the current user'
fi

if [[ ! -x "$real_home/.local/bin/hermes" || -d "$real_home/.local/bin/hermes" ]]; then
  fail "Hermes CLI is missing or not executable: $real_home/.local/bin/hermes"
fi

ensure_user_directory() {
  local directory="$1"
  local owner

  if [[ -L "$directory" ]]; then
    fail "refusing to write through a symlink directory: $directory"
  elif [[ -e "$directory" ]]; then
    [[ -d "$directory" ]] || fail "expected a directory: $directory"
  else
    mkdir -- "$directory" || fail "could not create directory: $directory"
  fi

  owner=$(stat -c '%u' -- "$directory") || fail "could not inspect directory: $directory"
  [[ "$owner" == "$user_id" ]] || fail "directory is not owned by the current user: $directory"
  [[ -w "$directory" && -x "$directory" ]] || fail "directory is not writable: $directory"
}

local_dir="$real_home/.local"
share_dir="$local_dir/share"
icon_dir="$share_dir/icons"
application_dir="$share_dir/applications"
ensure_user_directory "$local_dir"
ensure_user_directory "$share_dir"
ensure_user_directory "$icon_dir"
ensure_user_directory "$application_dir"

icon_path="$icon_dir/hermes-agent.png"
desktop_path="$application_dir/hermes.desktop"
validate_output_file() {
  local path="$1"
  local owner

  if [[ -L "$path" ]]; then
    fail "refusing to replace a symlink: $path"
  elif [[ -e "$path" ]]; then
    [[ -f "$path" ]] || fail "refusing to replace a non-file: $path"
    owner=$(stat -c '%u' -- "$path") || fail "could not inspect file: $path"
    [[ "$owner" == "$user_id" ]] || fail "file is not owned by the current user: $path"
  fi
}
validate_output_file "$icon_path"
validate_output_file "$desktop_path"

quote_exec_argument() {
  local value="$1"
  value=${value//\\/\\\\}
  value=${value//\"/\\\"}
  value=${value//\$/\\\$}
  value=${value//\`/\\\`}
  value=${value//%/%%}
  value=${value//\\/\\\\}
  printf '"%s"' "$value"
}

escape_desktop_string() {
  local value="$1"
  value=${value//\\/\\\\}
  value=${value//$'\n'/\\n}
  value=${value//$'\r'/\\r}
  value=${value//$'\t'/\\t}
  printf '%s' "$value"
}

exec_path=$(quote_exec_argument "$real_home/.local/bin/hermes")
icon_value=$(escape_desktop_string "$icon_path")

# Stage both complete files beside their destinations so each final rename is atomic.
tmp_icon=''
tmp_desktop=''
backup_icon=''
backup_desktop=''
retain_icon_backup=0
retain_desktop_backup=0
icon_existed=0
desktop_existed=0
icon_publish_attempted=0
desktop_publish_attempted=0
publish_icon=1
publish_desktop=1
commit_complete=0

cleanup() {
  local status=$?
  trap - EXIT HUP INT TERM

  if (( ! commit_complete )); then
    if (( desktop_publish_attempted )); then
      if (( desktop_existed )); then
        if mv -f -- "$backup_desktop" "$desktop_path"; then
          backup_desktop=''
        else
          printf 'hermes launcher: rollback failed; previous desktop entry is at %s\n' "$backup_desktop" >&2
          retain_desktop_backup=1
          status=1
        fi
      else
        rm -f -- "$desktop_path" || status=1
      fi
    fi
    if (( icon_publish_attempted )); then
      if (( icon_existed )); then
        if mv -f -- "$backup_icon" "$icon_path"; then
          backup_icon=''
        else
          printf 'hermes launcher: rollback failed; previous icon is at %s\n' "$backup_icon" >&2
          retain_icon_backup=1
          status=1
        fi
      else
        rm -f -- "$icon_path" || status=1
      fi
    fi
  fi

  [[ -z "$tmp_icon" ]] || rm -f -- "$tmp_icon" || status=1
  [[ -z "$tmp_desktop" ]] || rm -f -- "$tmp_desktop" || status=1
  (( retain_icon_backup )) || [[ -z "$backup_icon" ]] || rm -f -- "$backup_icon" || status=1
  (( retain_desktop_backup )) || [[ -z "$backup_desktop" ]] || rm -f -- "$backup_desktop" || status=1
  exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

tmp_icon=$(mktemp "$icon_dir/.hermes-agent-icon.XXXXXXXX") || fail "could not stage icon in $icon_dir"
tmp_desktop=$(mktemp "$application_dir/.hermes-agent-desktop.XXXXXXXX") || fail "could not stage desktop entry in $application_dir"

cp -- "$source_icon" "$tmp_icon" || fail 'could not copy the repo-local icon'
chmod 0644 -- "$tmp_icon" || fail 'could not set icon permissions'
{
  printf '[Desktop Entry]\n'
  printf 'Type=Application\n'
  printf 'Name=Hermes Agent\n'
  printf 'Exec=/usr/bin/qterminal -e %s\n' "$exec_path"
  printf 'Icon=%s\n' "$icon_value"
  printf 'Terminal=false\n'
  printf 'Categories=Development;\n'
} > "$tmp_desktop" || fail 'could not write the desktop entry'
chmod 0644 -- "$tmp_desktop" || fail 'could not set desktop entry permissions'

if [[ -e "$icon_path" ]]; then
  if cmp -s -- "$tmp_icon" "$icon_path" && [[ "$(stat -c '%a' -- "$icon_path")" == 644 ]]; then
    rm -f -- "$tmp_icon" || fail 'could not clean the unchanged staged icon'
    tmp_icon=''
    publish_icon=0
  else
    compare_status=$?
    [[ "$compare_status" -eq 0 || "$compare_status" -eq 1 ]] || fail 'could not compare the existing icon'
  fi
fi
if [[ -e "$desktop_path" ]]; then
  if cmp -s -- "$tmp_desktop" "$desktop_path" && [[ "$(stat -c '%a' -- "$desktop_path")" == 644 ]]; then
    rm -f -- "$tmp_desktop" || fail 'could not clean the unchanged staged desktop entry'
    tmp_desktop=''
    publish_desktop=0
  else
    compare_status=$?
    [[ "$compare_status" -eq 0 || "$compare_status" -eq 1 ]] || fail 'could not compare the existing desktop entry'
  fi
fi

if (( publish_icon )) && [[ -e "$icon_path" ]]; then
  icon_existed=1
  backup_icon=$(mktemp "$icon_dir/.hermes-agent-icon-backup.XXXXXXXX") \
    || fail "could not stage icon backup in $icon_dir"
  cp -p -- "$icon_path" "$backup_icon" || fail 'could not preserve the previous icon'
fi
if (( publish_desktop )) && [[ -e "$desktop_path" ]]; then
  desktop_existed=1
  backup_desktop=$(mktemp "$application_dir/.hermes-agent-desktop-backup.XXXXXXXX") \
    || fail "could not stage desktop entry backup in $application_dir"
  cp -p -- "$desktop_path" "$backup_desktop" || fail 'could not preserve the previous desktop entry'
fi

if (( publish_icon )); then
  icon_publish_attempted=1
  mv -f -- "$tmp_icon" "$icon_path" || fail 'could not publish the icon'
  tmp_icon=''
fi
if (( publish_desktop )); then
  desktop_publish_attempted=1
  mv -f -- "$tmp_desktop" "$desktop_path" || fail 'could not publish the desktop entry'
  tmp_desktop=''
fi
commit_complete=1
printf 'hermes launcher: installed %s\n' "$desktop_path"
