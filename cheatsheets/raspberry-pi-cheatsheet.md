# Raspberry Pi Cheatsheet

## System

### Quick Reference
| Command | Description |
|---------|-------------|
| `raspi-config` | Open Raspberry Pi configuration tool |
| `vcgencmd measure_temp` | Check CPU temperature |
| `vcgencmd get_throttled` | Check throttling status |
| `cat /proc/cpuinfo` | Show CPU info and Pi model |
| `uname -a` | Show kernel version |
| `df -h` | Show disk usage |
| `free -h` | Show memory usage |
| `uptime` | Show system uptime and load |

### Updates
| Command | Description |
|---------|-------------|
| `sudo apt update` | Refresh package lists |
| `sudo apt upgrade` | Upgrade installed packages |
| `sudo apt full-upgrade` | Full upgrade including kernel |
| `sudo rpi-update` | Update firmware (use with caution) |
| `sudo reboot` | Reboot the Pi |
| `sudo shutdown -h now` | Shut down the Pi |

## GPIO

### Pin Layout
| Command | Description |
|---------|-------------|
| `pinout` | Display GPIO pinout diagram |
| `gpio readall` | Show all GPIO pin states (WiringPi) |

### Python (RPi.GPIO)
```python
import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)       # Use BCM pin numbering
GPIO.setup(18, GPIO.OUT)     # Set pin 18 as output
GPIO.output(18, GPIO.HIGH)   # Set pin 18 high
GPIO.output(18, GPIO.LOW)    # Set pin 18 low
GPIO.input(18)               # Read pin 18
GPIO.cleanup()               # Reset all pins
```

### Python (gpiozero)
```python
from gpiozero import LED, Button
led = LED(18)
led.on()
led.off()
led.toggle()
btn = Button(17)
btn.wait_for_press()
```

## Networking

| Command | Description |
|---------|-------------|
| `hostname -I` | Show IP address(es) |
| `iwconfig` | Show wireless info |
| `nmcli dev wifi list` | List available Wi-Fi networks |
| `nmcli dev wifi connect <SSID> password <pw>` | Connect to Wi-Fi |
| `cat /etc/hostname` | Show hostname |
| `sudo hostnamectl set-hostname <name>` | Change hostname |

## SSH

| Command | Description |
|---------|-------------|
| `ssh pi@<ip>` | SSH into Pi (legacy user) |
| `ssh-keygen` | Generate SSH key pair |
| `ssh-copy-id pi@<ip>` | Copy public key to Pi |
| `sudo systemctl enable ssh` | Enable SSH on boot |
| `sudo systemctl start ssh` | Start SSH service |

## Storage

| Command | Description |
|---------|-------------|
| `lsblk` | List block devices |
| `sudo fdisk -l` | List disks and partitions |
| `sudo mount /dev/sda1 /mnt` | Mount a drive |
| `sudo umount /mnt` | Unmount a drive |
| `sudo dd if=<img> of=/dev/sdX bs=4M status=progress` | Write image to SD card |

## Services (systemd)

| Command | Description |
|---------|-------------|
| `sudo systemctl start <service>` | Start a service |
| `sudo systemctl stop <service>` | Stop a service |
| `sudo systemctl restart <service>` | Restart a service |
| `sudo systemctl enable <service>` | Enable service on boot |
| `sudo systemctl disable <service>` | Disable service on boot |
| `sudo systemctl status <service>` | Check service status |
| `journalctl -u <service> -f` | Follow service logs |

## Camera (libcamera)

| Command | Description |
|---------|-------------|
| `libcamera-still -o photo.jpg` | Capture a photo |
| `libcamera-vid -o video.h264 -t 5000` | Record 5s of video |
| `libcamera-hello` | Test camera with preview |

> **Default credentials (legacy):** user: `pi` / password: `raspberry`
