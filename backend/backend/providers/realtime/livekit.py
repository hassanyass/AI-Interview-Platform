"""LiveKit adapter for the realtime port."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import aiohttp
from livekit import api

from backend.providers.realtime.base import RealtimeProvider, RecordingStart
from backend.providers.storage.base import S3Destination

logger = logging.getLogger(__name__)


class LiveKitProvider(RealtimeProvider):
    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        api_secret: str,
        egress_layout: str = "speaker",
        egress_start_retry_attempts: int = 10,
        egress_start_retry_delay_seconds: float = 1.0,
        api_timeout_seconds: float = 10.0,
    ) -> None:
        self._api_timeout = api_timeout_seconds
        self._url = url
        self._api_key = api_key
        self._api_secret = api_secret
        self._layout = egress_layout
        self._retry_attempts = egress_start_retry_attempts
        self._retry_delay = egress_start_retry_delay_seconds

    def _api(self) -> api.LiveKitAPI:
        # One short-lived client per operation, closed by the caller of this
        # helper -- LiveKitAPI holds an aiohttp session bound to the loop.
        # Without a timeout aiohttp waits forever on a stalled LiveKit call.
        return api.LiveKitAPI(
            url=self._url, api_key=self._api_key, api_secret=self._api_secret,
            timeout=aiohttp.ClientTimeout(total=self._api_timeout),
        )

    def mint_participant_token(self, *, room: str, identity: str, name: str, ttl: timedelta) -> str:
        token = api.AccessToken(self._api_key, self._api_secret)
        token.with_ttl(ttl)
        token.with_identity(identity)
        token.with_name(name)
        token.with_grants(api.VideoGrants(room_join=True, room=room))
        return token.to_jwt()

    async def start_room_recording(self, *, room: str, output_path: str, destination: S3Destination) -> RecordingStart:
        req = api.RoomCompositeEgressRequest(
            room_name=room,
            layout=self._layout,
            file_outputs=[
                api.EncodedFileOutput(
                    file_type=api.EncodedFileType.MP4,
                    filepath=output_path,
                    s3=api.S3Upload(
                        access_key=destination.access_key,
                        secret=destination.secret,
                        bucket=destination.bucket,
                        region=destination.region,
                        endpoint=destination.endpoint,
                        force_path_style=destination.force_path_style,
                    ),
                )
            ],
        )
        lkapi = self._api()
        try:
            info = None
            for attempt in range(1, self._retry_attempts + 1):
                try:
                    info = await lkapi.egress.start_room_composite_egress(req)
                    break
                except api.ServerError as e:
                    # The room is created by the candidate's own connect, which
                    # normally lands 1-3 s after the token is issued.
                    if e.code != "not_found" or attempt == self._retry_attempts:
                        raise
                    logger.info("Egress start attempt %d/%d: room %s not ready yet, retrying",
                                attempt, self._retry_attempts, room)
                    await asyncio.sleep(self._retry_delay)
            assert info is not None
            return RecordingStart(
                egress_id=info.egress_id,
                failed=info.status in (api.EgressStatus.EGRESS_FAILED, api.EgressStatus.EGRESS_ABORTED),
                status=api.EgressStatus.Name(info.status),
                error=info.error or "",
            )
        finally:
            await lkapi.aclose()

    async def stop_recording(self, egress_id: str) -> None:
        lkapi = self._api()
        try:
            await lkapi.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))
        finally:
            await lkapi.aclose()

    async def delete_room(self, room: str) -> None:
        lkapi = self._api()
        try:
            await lkapi.room.delete_room(api.DeleteRoomRequest(room=room))
        finally:
            await lkapi.aclose()
