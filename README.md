# NAD Multi-room Audio Controller Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)


This integration integrates with NAD multi-room audio amplifiers.
It provides control over output volume, output muting, input selection, DSP presets and power cycling.

## Overview

One entity will be created for the controller itself, and one for each channel.

![An overview of all entities](images/Overview.png)

_The entity is named after the `Unit Name`, as configured in NAD's web interface.
In this case, that's 'Fortie'._

![A detail view of one channel](images/Detail_view.png)

_The detail view can be used to configure 
an output's volume, input channel selection and its sound mode,
as defined by its presets._

### Receiver entity

The receiver is only used to control the power. Available services:
* `media_player.turn_on`
* `media_player.turn_off`
* `media_player.toggle`
* `media_player.select_source`

Note that using the `select_source` on the receiver will override the channel specific source configuration,
until it's set back to 'None'.

### Channel entities

One channel is created for every output. Available services:
* `media_player.volume_up`
* `media_player.volume_down`
* `media_player.volume_set`
* `media_player.volume_mute`
* `media_player.select_source`
* `media_player.select_sound_mode`

## Compatible devices

* NAD Cl 16-60

## Setup

> **Note**
> 
> This integration requires [HACS](https://hacs.xyz/docs/setup/download/) to be installed

1. Open HACS
2. _+ EXPLORE & DOWNLOAD REPOSITORIES_
3. Find _NAD Multi-room Audio Controller_ in this list
4. _DOWNLOAD THIS REPOSITORY WITH HACS_
5. _DOWNLOAD_
6. Restart Home Assistant (_Settings_ > _System_ >  _RESTART_)

The flow can now proceed in one of two ways:

### Automatic flow

 1. Through UPNP, the controller can be discovered automatically.

![The 'New devices discovered' notification](images/Automatic_flow_0_notification.png)

 2. Either click the _Check it out_ link or navigate to _Settings_ > _Devices & Services_ to find the discovery.

![The 'Discovered' card, prompting to configure the new integration](images/Automatic_flow_1_discovery.png)

> **Note**
> 
> If this does not show up, please proceed with the _Manual installation_ flow

 3. After pressing _CONFIGURE_, a final confirmation is prompted.

![The 'Confirmation' dialog](images/Automatic_flow_2_confirmation.png)

 4. When _SUBMIT_ is pressed, success dialog should be shown.

![The 'Confirmation' dialog](images/Flow_success.png)

 5. After optionally setting its area and confirming with _FINISH_, the integration is now active and ready to be used.

### Manual flow

 1. Navigate to the integrations page: _Settings_ > _Devices & Services_
 2. _+ ADD INTEGRATION_
 3. Select _NAD Multi-room Audio Controller_ in this selection window

![The 'Find integration' selection window](images/Manual_flow_0_find_integration.png)

 4. Enter the IP and Port (52000 by default) and press _SUBMIT_

![The dialog prompting network parameters](images/Manual_flow_1_enter_network_params.png)

 5. After optionally setting its area and confirming with _FINISH_, the integration is now active and ready to be used.

![The 'Confirmation' dialog](images/Flow_success.png)