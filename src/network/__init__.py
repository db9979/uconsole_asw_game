"""Optionale Echtwelt-Netzwerk-Integration (AIS Stream, OpenSky ADS-B).

Alles hier ist strikt optional: ohne Internetverbindung oder API-Key bleibt
das Spiel unverändert. Netzwerk-I/O läuft ausschließlich in Daemon-Threads,
niemals im Pygame-Hauptthread.
"""
