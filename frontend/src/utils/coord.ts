/**
 * WGS-84（国际 GPS 坐标）→ GCJ-02（国测局坐标）
 *
 * 为什么需要这一步：
 *   OSRM 算出来的路线轨迹是 **WGS-84** 坐标，而高德地图的瓦片是 **GCJ-02**。
 *   两者在中国境内相差几百米（就是俗称的「火星坐标偏移」）。
 *   不转换的话，画出来的路线会整体偏离道路。
 *
 * 这是公开的经典换算算法，误差米级，画路线完全够用。
 * 注意：国内的地图服务（高德/腾讯）都是 GCJ-02；百度是再偏移一次的 BD-09。
 */

const A = 6378245.0 // 长半轴（米）
const EE = 0.00669342162296594323 // 偏心率平方

/** 中国范围外不做偏移 */
function outOfChina(lng: number, lat: number): boolean {
  return lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271
}

function transformLat(lng: number, lat: number): number {
  let ret =
    -100 +
    2 * lng +
    3 * lat +
    0.2 * lat * lat +
    0.1 * lng * lat +
    0.2 * Math.sqrt(Math.abs(lng))
  ret += ((20 * Math.sin(6 * lng * Math.PI) + 20 * Math.sin(2 * lng * Math.PI)) * 2) / 3
  ret += ((20 * Math.sin(lat * Math.PI) + 40 * Math.sin((lat / 3) * Math.PI)) * 2) / 3
  ret += ((160 * Math.sin((lat / 12) * Math.PI) + 320 * Math.sin((lat * Math.PI) / 30)) * 2) / 3
  return ret
}

function transformLng(lng: number, lat: number): number {
  let ret =
    300 + lng + 2 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * Math.sqrt(Math.abs(lng))
  ret += ((20 * Math.sin(6 * lng * Math.PI) + 20 * Math.sin(2 * lng * Math.PI)) * 2) / 3
  ret += ((20 * Math.sin(lng * Math.PI) + 40 * Math.sin((lng / 3) * Math.PI)) * 2) / 3
  ret += ((150 * Math.sin((lng / 12) * Math.PI) + 300 * Math.sin((lng / 30) * Math.PI)) * 2) / 3
  return ret
}

/** 传经度、纬度，返回 [经度, 纬度]（已偏移） */
export function wgs84ToGcj02(lng: number, lat: number): [number, number] {
  if (outOfChina(lng, lat)) return [lng, lat]

  // 这里的 lng-105 / lat-35 是算法里固定的基准点
  const dLat = transformLat(lng - 105.0, lat - 35.0)
  const dLng = transformLng(lng - 105.0, lat - 35.0)

  const radLat = (lat / 180.0) * Math.PI
  let magic = Math.sin(radLat)
  magic = 1 - EE * magic * magic
  const sqrtMagic = Math.sqrt(magic)

  const newLat = lat + (dLat * 180.0) / (((A * (1 - EE)) / (magic * sqrtMagic)) * Math.PI)
  const newLng = lng + (dLng * 180.0) / ((A / sqrtMagic) * Math.cos(radLat) * Math.PI)
  return [newLng, newLat]
}
