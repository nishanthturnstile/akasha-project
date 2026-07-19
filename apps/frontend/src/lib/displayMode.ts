/** Human label for an internal display-mode token (e.g. `VV_GRAYSCALE` -> `Backscatter`). */
export function modeLabel(mode: string): string {
    switch (mode) {
        case 'RGB':
            return 'True colour';
        case 'NDVI':
            return 'NDVI';
        case 'NDRE':
            return 'NDRE';
        case 'MSAVI':
            return 'MSAVI';
        case 'NDMI':
            return 'NDMI';
        case 'FALSE_COLOR_URBAN':
            return 'False colour';
        case 'FALSE_COLOR':
            return 'False colour';
        case 'VV_GRAYSCALE':
        case 'BACKSCATTER':
            return 'Backscatter';
        case 'VH_GRAYSCALE':
            return 'VH';
        default:
            return mode.replace(/_/g, ' ');
    }
}
