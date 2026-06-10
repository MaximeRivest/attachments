# demo.tape — records scripts/demo.py into demo.gif with VHS.
#
# Install vhs (https://github.com/charmbracelet/vhs):
#   brew install vhs                      # macOS
#   go install github.com/charmbracelet/vhs@latest   # or Go
#   # Linux: download a release binary, needs ttyd + ffmpeg on PATH
#
# Record (from the repo root):
#   vhs scripts/demo.tape
#
# Produces demo.gif in the repo root (~75s of footage).

Output demo.gif

Set FontSize 16
Set Width 1100
Set Height 700
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms

Type "uv run python scripts/demo.py"
Enter

# The script paces itself with built-in pauses (~60s) — just wait it out.
Sleep 75s
