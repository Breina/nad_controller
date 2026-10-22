"""Base entities for the NAD multi-room audio controller."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import NadCoordinator
from .nad_client import Zone

try:
    from homeassistant.helpers.device_registry import ChildDeviceInfo
except ImportError:  # Home Assistant before 2026.8
    ChildDeviceInfo = None


def amp_device_info(coordinator: NadCoordinator) -> DeviceInfo:
    identity = coordinator.identity
    return DeviceInfo(
        configuration_url=f"http://{coordinator.client.host}",
        identifiers={(DOMAIN, identity.serial_number)},
        manufacturer=MANUFACTURER,
        model=identity.model,
        name=identity.name,
        serial_number=identity.serial_number,
        sw_version=coordinator.data.firmware_version or identity.firmware_version,
    )


class NadEntity(CoordinatorEntity[NadCoordinator]):
    """An entity of the amplifier itself."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NadCoordinator, key: str | None = None):
        super().__init__(coordinator)
        self._serial_number = coordinator.identity.serial_number
        # Matches the unique ids of earlier versions, so existing entities keep their ids and history
        self._attr_unique_id = f"{DOMAIN}_{self._serial_number}" + (f"_{key}" if key else "")
        self._attr_device_info = amp_device_info(coordinator)


class NadZoneEntity(NadEntity):
    """An entity of one zone, which gets a device of its own so it can be placed in an area."""

    def __init__(self, coordinator: NadCoordinator, zone: Zone, key: str | None = None):
        super().__init__(coordinator, f"zone_{zone.index}" + (f"_{key}" if key else ""))
        self._zone_index = zone.index
        identifiers = {(DOMAIN, f"{self._serial_number}_zone_{zone.index}")}
        if ChildDeviceInfo is not None:
            self._attr_device_info = ChildDeviceInfo(
                identifiers=identifiers,
                name=zone.name,
                parent_device_id=coordinator.device_id,
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers=identifiers,
                manufacturer=MANUFACTURER,
                model=f"{coordinator.identity.model} zone",
                name=zone.name,
                via_device=(DOMAIN, self._serial_number),
            )

    @property
    def zone(self) -> Zone | None:
        return next((z for z in self.coordinator.data.zones if z.index == self._zone_index), None)

    @property
    def available(self) -> bool:
        return super().available and self.zone is not None
