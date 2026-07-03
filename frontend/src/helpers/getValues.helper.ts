export const getValues = (startAt: number, duration: number, offset = 50) => {
  let left = startAt - offset;
  let right = startAt + offset;

  // Nếu left < 0 thì dịch cả 2 biên sang phải
  if (left < 0) {
    right += -left; // tăng right để giữ startAt ở giữa
    left = 0;
  }

  // Nếu right > duration thì dịch ngược lại sang trái
  if (right > duration) {
    const diff = right - duration;
    left = Math.max(0, left - diff);
    right = duration;
  }

  return [left, startAt, right];
};