# Local overrides migrated from /etc/fish/config.fish
# By moving here, these survive system package updates

set -gx no_proxy 127.0.0.1
set -x EDITOR nvim
set -x PUB_HOSTED_URL "https://pub.flutter-io.cn"
set -x FLUTTER_STORAGE_BASE_URL "https://storage.flutter-io.cn"

alias nv nvim
alias pacman='sudo -E pacman'
alias g='tgpt'
alias nano='micro'
alias cd='z'

# carapace completions
set -Ux CARAPACE_BRIDGES 'zsh,fish,bash,inshellisense'
carapace _carapace | source
