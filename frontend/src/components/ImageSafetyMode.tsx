import { createContext, useContext, type ReactNode } from "react";

interface ImageSafetyModeValue {
  imageSafetyModeEnabled: boolean;
  setImageSafetyModeEnabled: (enabled: boolean) => void;
}

const ImageSafetyModeContext = createContext<ImageSafetyModeValue>({
  imageSafetyModeEnabled: true,
  setImageSafetyModeEnabled: () => undefined,
});

export function ImageSafetyModeProvider({
  children,
  enabled,
  onChange,
}: {
  children: ReactNode;
  enabled: boolean;
  onChange: (enabled: boolean) => void;
}) {
  return (
    <ImageSafetyModeContext.Provider
      value={{
        imageSafetyModeEnabled: enabled,
        setImageSafetyModeEnabled: onChange,
      }}
    >
      {children}
    </ImageSafetyModeContext.Provider>
  );
}

export function useImageSafetyMode() {
  return useContext(ImageSafetyModeContext);
}
