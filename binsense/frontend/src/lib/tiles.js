// Слой подложки карты. По умолчанию — OpenStreetMap.
// Для закрытого контура можно поднять свой tile-сервер и заменить адрес здесь.
export const TILE_URL =
  import.meta.env.VITE_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'

export const TILE_ATTRIBUTION =
  import.meta.env.VITE_TILE_ATTRIBUTION ||
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
