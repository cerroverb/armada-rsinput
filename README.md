Builds the rsinput controller driver for Armada images with the input patches from armada-os/armada#944 and #945 (report rate, gyro node, Xbox face codes, in-kernel back paddles, Quick Access chord), for devices that run those patches before Armada ships them.

Every three hours the workflow looks at the last 300 commits of Armada's main and beta branches. For each kernel it has not built yet, it takes that commit's packages/kernel (kernel version, patch series, config fragment), adds the patches from the two PR branches on cerroverb/armada, and builds rsinput.ko in a Fedora 44 container, the same way Armada's packages/kernel/scripts/build-kernel.sh prepares its tree. The modules and index.json go to the "modules" release. index.json maps each image commit (the part of IMAGE_VERSION after the dot) to its module and that module's sha256.

On a device, the swap script in the rsinput-gyro setup reads index.json after a kernel update, checks the sha256 and the vermagic against the kernel's own rsinput.ko, and loads the module. Without a matching build it keeps Armada's driver and tries again later.

build-module.sh builds one module, update-index.py decides what to build and writes the index.

Code in this repository was written with the help of an LLM (Claude) and reviewed and tested on an Odin 3 Portal, Odin 3 Ultra and Thor Max.
