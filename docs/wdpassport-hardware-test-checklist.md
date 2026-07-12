# WD Passport Hardware Test Checklist

Use a non-critical WD My Passport drive first. Do not run erase on any drive
that contains data you need.

1. Confirm the OS sees the device:

   ```bash
   lsblk
   ```

2. Check WD status:

   ```bash
   sudo wdpassport status --device /dev/sdX
   ```

3. Unlock a locked test drive:

   ```bash
   sudo wdpassport unlock --device /dev/sdX
   ```

4. Disable firmware standby before a long copy:

   ```bash
   sudo wdpassport sleep off --device /dev/sdX
   ```

5. Run active keep-awake during a long copy in another terminal:

   ```bash
   sudo wdpassport keep-awake --device /dev/sdX --interval 60
   ```

6. Check model-specific controls:

   ```bash
   sudo wdpassport vcd status --device /dev/sdX
   sudo wdpassport led status --device /dev/sdX
   sudo wdpassport self-test --device /dev/sdX
   ```

7. Launch the GUI:

   ```bash
   sudo wdpassport-gui
   ```

8. Secure erase only on a sacrificial drive:

   ```bash
   sudo wdpassport erase --device /dev/sdX
   ```

After erase, verify the drive appears blank and recreate partitioning with the
disk tool you normally use.
