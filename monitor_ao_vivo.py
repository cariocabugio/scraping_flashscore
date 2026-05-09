#!/usr/bin/env python3
import sys
import asyncio
import random
import re
from flashscore.fetcher import fetch_feed, extract_match_id, API_URL_H2H, HEADERS
from flashscore.parser import parse_live_stats, parse_live_time, parse_h2h
from flashscore.telegram_sender import send_telegram
from safe_requests import safe_get

STATS_URL = "https://global.flashscore.ninja/401/x/feed/df_st_1_{match_id}"
DETAIL_URL = "https://global.flashscore.ninja/401/x/feed/dc_1_{match_id}"

ALERTED = {}

def compute_corners_projection(total_corners_now: int, current_minute: int, match_duration: int = 90, cap: int = 15) -> float:
    if current_minute <= 0:
        return min(float(total_corners_now), cap)
    rate_per_minute = total_corners_now / current_minute
    minutes_left = max(0, match_duration - current_minute)
    projected_total = total_corners_now + rate_per_minute * minutes_left
    return min(projected_total, cap)

def parse_xg(text: str):
    if not text:
        return None, None
    match = re.search(r'Gols esperados \(xG\)¬SH÷([\d.]+)¬SI÷([\d.]+)', text)
    if match:
        try:
            return float(match.group(1)), float(match.group(2))
        except:
            pass
    return None, None

def compute_goals_projection(current_home_xg: float, current_away_xg: float, current_minute: int, match_duration: int = 90) -> float:
    if current_minute <= 0 or (current_home_xg + current_away_xg) == 0:
        return 0.0
    total_xg = current_home_xg + current_away_xg
    rate_per_minute = total_xg / current_minute
    minutes_left = max(0, match_duration - current_minute)
    return total_xg + rate_per_minute * minutes_left

async def monitor_match(match_id: str):
    print(f"🔍 Iniciando monitoramento para {match_id}...")

    raw_h2h = fetch_feed(API_URL_H2H, match_id)
    home_name, away_name = "Time A", "Time B"
    if raw_h2h:
        data = parse_h2h(raw_h2h, max_games=1)
        if len(data) >= 2:
            home_name, away_name = list(data.keys())[:2]

    stop_alerted = False

    while True:
        try:
            detail_raw = safe_get(DETAIL_URL.format(match_id=match_id), headers=HEADERS)
            if not detail_raw:
                await asyncio.sleep(60 + random.uniform(0, 15))
                continue

            status, minute = parse_live_time(detail_raw)
            if status is None or minute is None:
                await asyncio.sleep(60 + random.uniform(0, 15))
                continue

            if status != 2:
                if not stop_alerted:
                    await send_telegram(f"🏁 {home_name} x {away_name}: Partida encerrada. Status {status}.")
                    stop_alerted = True
                print("🏁 Partida encerrada. Monitoramento finalizado.")
                break

            if minute < 20:
                print(f"⏱️ {minute}' (aguardando 20' para projeções)")
                await asyncio.sleep(60 + random.uniform(0, 15))
                continue

            live_raw = safe_get(STATS_URL.format(match_id=match_id), headers=HEADERS)
            if not live_raw:
                await asyncio.sleep(60 + random.uniform(0, 15))
                continue

            home_c, away_c = parse_live_stats(live_raw)
            total_c = home_c + away_c if home_c is not None and away_c is not None else 0
            home_xg, away_xg = parse_xg(live_raw)

            corners_proj = compute_corners_projection(total_c, minute) if home_c is not None else 0
            goals_proj = compute_goals_projection(home_xg, away_xg, minute) if home_xg is not None else None

            print(f"⏱️ {minute}' | Cantos: {home_c}x{away_c} (total {total_c}) | Projeção cantos: {corners_proj:.1f}", end="")
            if goals_proj is not None:
                print(f" | xG: {home_xg:.2f} x {away_xg:.2f} | Projeção gols: {goals_proj:.2f}")
            else:
                print(" | xG indisponível")

            # ALERTAS DE ESCANTEIOS
            # Overs
            over_thresholds = [(8.5, "+8.5"), (9.5, "+9.5"), (10.5, "+10.5")]
            under_thresholds = {
                "8.5": (5.5, "Under 8.5"),   # se projeção <= 5.5, sugere Under 8.5
                "9.5": (6.5, "Under 9.5"),
                "10.5": (7.5, "Under 10.5")
            }
            for thr, label in over_thresholds:
                key = (match_id, f"corners_over_{label}")
                if corners_proj > thr:
                    if not ALERTED.get(key):
                        msg = (f"🚨 Alerta de ESCANTEIOS ({home_name} x {away_name})\n"
                               f"⏱️ {minute}° minuto\n"
                               f"📊 Total atual: {total_c} ({home_c} x {away_c})\n"
                               f"📈 Projeção final: {corners_proj:.1f} (>{thr})\n"
                               f"💡 Aposta sugerida: Cantos +{label}")
                        await send_telegram(msg)
                        ALERTED[key] = True
                        print(f"📤 Alerta enviado: Cantos +{label}")
                else:
                    ALERTED.pop(key, None)

                # Under correspondente
                if thr in under_thresholds:
                    under_limit, under_label = under_thresholds[thr]
                    under_key = (match_id, f"corners_under_{under_label}")
                    if corners_proj <= under_limit:
                        if not ALERTED.get(under_key):
                            msg = (f"🚨 Alerta de ESCANTEIOS ({home_name} x {away_name})\n"
                                   f"⏱️ {minute}° minuto\n"
                                   f"📊 Total atual: {total_c} ({home_c} x {away_c})\n"
                                   f"📉 Projeção final: {corners_proj:.1f} (baixa)\n"
                                   f"💡 Aposta sugerida: Cantos {under_label}")
                            await send_telegram(msg)
                            ALERTED[under_key] = True
                            print(f"📤 Alerta enviado: Cantos {under_label}")
                    else:
                        ALERTED.pop(under_key, None)

            # ALERTAS DE GOLS
            if goals_proj is not None:
                # Overs
                over_goals = [(0.5, "Over 0.5"), (1.5, "Over 1.5"), (2.5, "Over 2.5")]
                under_goals = {
                    "0.5": (0.3, "Under 0.5"),
                    "1.5": (1.3, "Under 1.5"),
                    "2.5": (2.3, "Under 2.5")
                }
                for thr, label in over_goals:
                    key = (match_id, f"goals_over_{label}")
                    if goals_proj > thr:
                        if not ALERTED.get(key):
                            msg = (f"🚨 Alerta de GOLS ({home_name} x {away_name})\n"
                                   f"⏱️ {minute}° minuto\n"
                                   f"📊 xG atual: {home_xg:.2f} x {away_xg:.2f}\n"
                                   f"📈 Projeção total de gols: {goals_proj:.2f} (>{thr})\n"
                                   f"💡 Aposta sugerida: {label}")
                            await send_telegram(msg)
                            ALERTED[key] = True
                            print(f"📤 Alerta enviado: {label}")
                    else:
                        ALERTED.pop(key, None)

                    # Under
                    if thr in under_goals:
                        under_limit, under_label = under_goals[thr]
                        under_key = (match_id, f"goals_under_{under_label}")
                        if goals_proj <= under_limit:
                            if not ALERTED.get(under_key):
                                msg = (f"🚨 Alerta de GOLS ({home_name} x {away_name})\n"
                                       f"⏱️ {minute}° minuto\n"
                                       f"📊 xG atual: {home_xg:.2f} x {away_xg:.2f}\n"
                                       f"📉 Projeção total de gols: {goals_proj:.2f} (baixa)\n"
                                       f"💡 Aposta sugerida: {under_label}")
                                await send_telegram(msg)
                                ALERTED[under_key] = True
                                print(f"📤 Alerta enviado: {under_label}")
                        else:
                            ALERTED.pop(under_key, None)

                # Ambos marcam / Ambos não marcam
                if home_xg > 0.4 and away_xg > 0.4:
                    key = (match_id, "btts")
                    if not ALERTED.get(key):
                        msg = (f"🚨 Alerta de GOLS ({home_name} x {away_name})\n"
                               f"⏱️ {minute}° minuto\n"
                               f"📊 xG atual: {home_xg:.2f} x {away_xg:.2f}\n"
                               f"🟢 Ambos com boas chances (xG > 0.4)\n"
                               f"💡 Aposta sugerida: Ambos marcam (BTTS)")
                        await send_telegram(msg)
                        ALERTED[key] = True
                        print("📤 Alerta enviado: Ambos marcam (BTTS)")
                elif home_xg < 0.2 and away_xg < 0.2:
                    key = (match_id, "both_no_goal")
                    if not ALERTED.get(key):
                        msg = (f"🚨 Alerta de GOLS ({home_name} x {away_name})\n"
                               f"⏱️ {minute}° minuto\n"
                               f"📊 xG atual: {home_xg:.2f} x {away_xg:.2f}\n"
                               f"🔴 Ambos com chances muito baixas\n"
                               f"💡 Aposta sugerida: Ambos não marcam")
                        await send_telegram(msg)
                        ALERTED[key] = True
                        print("📤 Alerta enviado: Ambos não marcam")

            await asyncio.sleep(60 + random.uniform(0, 15))

        except KeyboardInterrupt:
            print("⏹️ Monitoramento interrompido pelo usuário.")
            break
        except Exception as e:
            print(f"❌ Erro no loop: {e}")
            await asyncio.sleep(30)

async def main():
    if len(sys.argv) < 2:
        print("Uso: python monitor_ao_vivo.py <ID_PARTIDA>")
        return
    match_id = extract_match_id(sys.argv[1])
    if not match_id:
        print("ID inválido.")
        return
    await monitor_match(match_id)

if __name__ == '__main__':
    asyncio.run(main())