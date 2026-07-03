import rawMapping from "../../src/mapping/video_drive_mapping.json"

const mapping: Record<string, string> = rawMapping;

export function getFileIdByVideoId(videoId: string): string  {
  return mapping[videoId] ;
}