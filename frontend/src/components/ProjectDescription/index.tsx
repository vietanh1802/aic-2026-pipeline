import Magnet from "../../Animations/Magnet/Magnet";
import GradientText from "../../TextAnimations/GradientText/GradientText";

type ProjectDescriptionProps = {
  isQuery?: boolean;
};

export default function ProjectDescription({
  isQuery = false,
}: ProjectDescriptionProps) {
  return (
    <div
      className={`${
        !isQuery ? "block" : "hidden"
      } flex items-center justify-center min-h-[60vh]`}
    >
      <Magnet padding={100} disabled={false} magnetStrength={6}>
        <GradientText
          colors={["#2EE550", "#0D9EA9", "#2EE550", "#0D9EA9", "#2EE550"]}
          animationSpeed={8}
          showBorder={false}
          className="font-baloo text-4xl font-bold"
        >
          Describe the scene.
          <br />
          We’ll locate the clip.
        </GradientText>
      </Magnet>
    </div>
  );
}
