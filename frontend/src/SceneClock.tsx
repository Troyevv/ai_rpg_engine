import {
  Sunrise,
  Sun,
  Sunset,
  Moon,
  Cloud,
  CloudSun,
  CloudDrizzle,
  CloudRain,
  CloudRainWind,
  CloudLightning,
  CloudSnow,
  Snowflake,
  CloudFog,
  Wind,
  ThermometerSun,
  Thermometer,
} from "lucide-react";
import type { Save } from "./types";
import { profileDate } from "./gameDate";
export type Weather = {
  condition: string;
  temperature: number | null;
  unit: string;
  forecast: boolean;
};
const conditions = {
  clear: [Sun, "Ясно"],
  partly_cloudy: [CloudSun, "Переменная облачность"],
  cloudy: [Cloud, "Облачно"],
  drizzle: [CloudDrizzle, "Морось"],
  rain: [CloudRain, "Дождь"],
  heavy_rain: [CloudRainWind, "Ливень"],
  thunderstorm: [CloudLightning, "Гроза"],
  snow: [CloudSnow, "Снег"],
  heavy_snow: [Snowflake, "Сильный снег"],
  sleet: [CloudRainWind, "Мокрый снег"],
  fog: [CloudFog, "Туман"],
  windy: [Wind, "Ветрено"],
  heat_extreme: [ThermometerSun, "Сильная жара"],
  cold_extreme: [Thermometer, "Сильный мороз"],
} as const;
export function WeatherBadge({
  weather,
  compact = false,
}: {
  weather?: Weather | null;
  compact?: boolean;
}) {
  if (!weather) return null;
  const pair = conditions[weather.condition as keyof typeof conditions];
  if (!pair) return null;
  const [Icon, label] = pair;
  return (
    <span className="weather-badge" title={label} aria-label={label}>
      <Icon size={16} />
      {!compact && (
        <>
          {label}
          {weather.temperature !== null
            ? ` · ${weather.temperature}°${weather.unit}`
            : ""}
        </>
      )}
    </span>
  );
}
export function SceneClock({
  save,
  fallback,
}: {
  save?: Save | null;
  fallback?: string;
}) {
  const time = save?.state.world_clock?.projection;
  if (!time) return <>{fallback || "Время не указано"}</>;
  const parts = {
    morning: [Sunrise, "Утро"],
    afternoon: [Sun, "День"],
    evening: [Sunset, "Вечер"],
    night: [Moon, "Ночь"],
  } as const;
  const [Icon, label] =
    parts[time.day_period as keyof typeof parts] || parts.night;
  return (
    <span className="scene-clock">
      <Icon size={16} aria-label={label} />
      <span>
        {time.date
          ? profileDate(
              time.date,
              (save?.state.world_clock?.calendar as any)?.profile,
              "weekday",
            )
          : `День ${time.day}`}{" "}
        · {time.time}
      </span>
      <WeatherBadge weather={(save?.state.scene_meta as any)?.weather} />
    </span>
  );
}
