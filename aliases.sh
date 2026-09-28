# Polymarket CLI shell aliases
# Source this from your ~/.bashrc or ~/.zshrc:
#   echo 'source /opt/data/polymarket-cli/aliases.sh' >> ~/.bashrc
#
# Assumes the script is on PATH (symlink to /usr/local/bin/polymarket)
# or accessible via `python3 /opt/data/polymarket-cli/polymarket.py`.

# Adjust this if polymarket is not on PATH
if command -v polymarket >/dev/null 2>&1; then
    PM=polymarket
else
    PM="python3 /opt/data/polymarket-cli/polymarket.py"
fi

# Discovery
alias pmsearch='$PM search'
alias pmtrending='$PM trending'
alias pmmarket='$PM market'
alias pmevent='$PM event'

# Prices / book
alias pmprice='$PM price'
alias pmbook='$PM book'
alias pmhistory='$PM history'
alias pmtoken='$PM token'
alias pmquick='$PM quick'

# Trades
alias pmtrades='$PM trades'

# Common workflows
# pmwatch <slug> — quick view, refreshable
pmwatch() {
    local slug="${1:?usage: pmwatch <market_slug>}"
    watch -n 5 "$PM quick '$slug' --depth 3"
}

# pmtop — top N markets by volume with their slugs (for piping)
pmtop() {
    local n="${1:-10}"
    $PM trending --limit "$n" --json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for i, evt in enumerate(data, 1):
    print(f\"{i}. {evt['title']}  vol=\${evt.get('volume', 0):,.0f}\")
    for m in evt.get('markets', [])[:3]:
        print(f\"   {m.get('slug', '')}\")
"
}

# pmlookup <query> — print slugs only, one per line (for piping into pmmarket/pmquick)
pmslugs() {
    local q="${1:?usage: pmslugs <query>}"
    $PM search "$q" --limit 20 --json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for evt in data.get('events', []):
    for m in evt.get('markets', []):
        if m.get('slug'):
            print(m['slug'])
"
}
