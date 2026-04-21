# Tmux Cheatsheet

## TMUX

### Quick Reference
| Command | Description |
|---------|-------------|
| `tmux new -s <name>` | Start a named session |
| `tmux ls` | List sessions |
| `tmux attach -t <name>` | Attach to a session |
| `tmux kill-session -t <name>` | Kill a session |
| `Prefix + %` | Split pane vertically |
| `Prefix + "` | Split pane horizontally |
| `Prefix + arrow` | Switch between panes |
| `Prefix + x` | Kill pane |
| `Prefix + &` | Kill window |

### Sessions
| Command | Description |
|---------|-------------|
| `tmux` | Start a new session |
| `tmux new -s <name>` | Start a named session |
| `tmux ls` | List sessions |
| `tmux attach -t <name>` | Attach to a session |
| `tmux kill-session -t <name>` | Kill a session |
| `Prefix + d` | Detach from session |
| `Prefix + $` | Rename session |
| `Prefix + s` | List/switch sessions |

### Windows (Tabs)
| Command | Description |
|---------|-------------|
| `Prefix + c` | Create new window |
| `Prefix + ,` | Rename window |
| `Prefix + w` | List windows |
| `Prefix + n` | Next window |
| `Prefix + p` | Previous window |
| `Prefix + <number>` | Switch to window by number |
| `Prefix + &` | Kill window |

### Panes
| Command | Description |
|---------|-------------|
| `Prefix + %` | Split pane vertically |
| `Prefix + "` | Split pane horizontally |
| `Prefix + arrow` | Switch between panes |
| `Prefix + z` | Toggle pane zoom |
| `Prefix + x` | Kill pane |
| `Prefix + q` | Show pane numbers |
| `Prefix + {` | Move pane left |
| `Prefix + }` | Move pane right |
| `Prefix + Space` | Toggle pane layouts |

### Resizing Panes
Open the tmux command prompt with `Prefix + :` then enter a `resize-pane` command.

| Command | Description |
|---------|-------------|
| `resize-pane -D 10` | Resize down by 10 cells (use `-U`, `-L`, `-R` for up/left/right) |
| `resize-pane -y 25%` | Set height to 25% of the window (use `-x` for width) |
| `resize-pane -t 1 -R 20` | Resize pane #1 to the right by 20 cells |

### Copy Mode
| Command | Description |
|---------|-------------|
| `Prefix + [` | Enter copy mode |
| `q` | Exit copy mode |
| `Space` | Start selection |
| `Enter` | Copy selection |
| `Prefix + ]` | Paste |

> **Default prefix:** `Ctrl + b`
