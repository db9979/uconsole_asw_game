"""Shared hand-built v2 fixture parts for Remote Crew tests."""

# A valid common ``weather_station`` block (no bathythermograph yet), matching
# src/commander/projections._weather_station and the browser validator.
WEATHER_STATION = dict(
    atmosphere=dict(
        weather="clear", precipitation="none", rain_intensity=0.0, visibility_nm=24.0,
        sea_state=2, wind_from_deg=245.0, wind_kn=12.0, gust_kn=16.0, beaufort=4,
        pressure_hpa=1010.0, pressure_tendency_hpa_3h=0.0, pressure_trend="steady",
        storm_warning=False, air_temp_c=12.0, sea_temp_c=13.0, cloud_cover=0.25,
        ceiling_ft=None, icing="none", sun_elevation_deg=30.0, daylight="day",
        moon_phase="full", moon_illumination=1.0, time="12:00"),
    effects=dict(solar_heating=True, wind_mixing=False, freshwater=False),
    flight=dict(
        status="clear", launch_safe=True, dipping_safe=True, deck_safe=True,
        wind_kn=12.0, gust_kn=16.0, crosswind_kn=4.0, visibility_nm=24.0,
        ceiling_ft=None, icing="none", sea_state=2, roll_deg=0.5, pitch_deg=0.3,
        limits=dict(wind_kn=32.0, gust_kn=40.0, crosswind_kn=22.0, visibility_nm=2.0,
                    ceiling_ft=300.0, sea_state=5.0, roll_deg=8.0, pitch_deg=3.5)),
    profile=None)


# The shared crew plot (src/commander/projections._plot), one object of each
# kind so the browser draws and lists every shape.
PLOT = dict(objects=[
    dict(id=1, shape="mark", label="M1", t=0.0, x=250.0, y=250.0),
    dict(id=2, shape="ruler", label="R2", t=0.0, x=250.0, y=250.0, x2=255.0, y2=246.0),
    dict(id=3, shape="bearing", label="B3", t=0.0, x=250.0, y=250.0, bearing=45.0),
    dict(id=4, shape="circle", label="C4", t=0.0, x=252.0, y=252.0, radius_nm=3.0),
    dict(id=5, shape="dr", label="D5", t=0.0, x=240.0, y=250.0, course=90.0,
         speed_kn=10.0, now_x=241.0, now_y=250.0, cpa_nm=0.5, cpa_s=120.0),
], max_objects=64, max_label=24, trail=[[249.0, 251.0], [249.5, 250.5]],
    fx=dict(pings=[[4.0, 250.0, 250.0]], echoes=[], splashes=[[2.0, 251.0, 249.0]]))

# Noise discipline of a crew without microphones (projections._crew_noise).
CREW_NOISE = {"voice": 0, "safe": 5, "loud": 11, "max": 20, "quiet": False}
