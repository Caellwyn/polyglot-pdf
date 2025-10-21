/**
 * Version Information
 */

// Version will be replaced by build process
export const VERSION = '1.0.0'
export const BUILD_DATE = new Date().toISOString()

export function getVersion(): string {
	return `${VERSION} (${BUILD_DATE})`
}
