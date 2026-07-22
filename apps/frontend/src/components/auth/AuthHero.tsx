import { BrandLockup } from '@/components/BrandLockup';

interface AuthHeroProps {
  description: string;
  imagePosition?: string;
  imageSrc: string;
  title: string;
}

/**
 * Shared, image-led auth panel. The image is decorative because the adjacent
 * copy communicates the same purpose to assistive technology.
 */
export function AuthHero({
  description,
  imagePosition = 'center',
  imageSrc,
  title,
}: AuthHeroProps) {
  return (
    <section className="auth-hero relative hidden min-h-0 overflow-hidden border-r border-border lg:block">
      <img
        alt=""
        aria-hidden="true"
        className="absolute inset-0 size-full object-cover"
        loading="eager"
        src={ imageSrc }
        style={ { objectPosition: imagePosition } }
      />
      <div className="auth-hero-scrim absolute inset-0" aria-hidden="true" />
      <div className="grid-pattern absolute inset-0 opacity-25" aria-hidden="true" />

      <div className="relative flex h-full flex-col justify-between p-10 xl:p-12">
        <BrandLockup variant="full" tone="inverse" />
        <div className="max-w-2xl rounded-xl border border-on-image/20 bg-background/10 p-6 text-on-image shadow-e2 backdrop-blur-sm">
          <p className="font-display text-4xl font-bold leading-tight text-balance xl:text-5xl">
            { title }
          </p>
          <p className="mt-4 max-w-xl text-sm leading-6 text-on-image/80 xl:text-base xl:leading-7">
            { description }
          </p>
        </div>
      </div>
    </section>
  );
}
