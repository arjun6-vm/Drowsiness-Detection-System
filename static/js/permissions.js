// SafeDrive Unified Real-Time Browser Permissions Monitor
const SafeDrivePermissions = {
    cameraStatus: 'prompt',    // 'granted' | 'denied' | 'prompt' | 'unsupported'
    locationStatus: 'prompt',  // 'granted' | 'denied' | 'prompt' | 'unsupported'
    listeners: [],
    camStatusObj: null,
    locStatusObj: null,

    subscribe(callback) {
        if (typeof callback === 'function') {
            this.listeners.push(callback);
            try {
                callback({
                    camera: this.cameraStatus,
                    location: this.locationStatus
                });
            } catch (err) {
                console.warn('SafeDrivePermissions subscribe error:', err);
            }
        }
    },

    notify() {
        const state = {
            camera: this.cameraStatus,
            location: this.locationStatus
        };
        this.listeners.forEach(cb => {
            try {
                cb(state);
            } catch (err) {
                console.warn('SafeDrivePermissions listener error:', err);
            }
        });
        window.dispatchEvent(new CustomEvent('safedrivePermissionsChanged', { detail: state }));
    },

    async checkCamera() {
        const prev = this.cameraStatus;
        if (navigator.permissions && navigator.permissions.query) {
            try {
                const res = await navigator.permissions.query({ name: 'camera' });
                this.camStatusObj = res;
                this.cameraStatus = res.state;
                res.onchange = () => {
                    this.cameraStatus = res.state;
                    this.notify();
                };
            } catch (err) {
                // If query is unsupported in some browsers (e.g. Firefox), test mediaDevices
                if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
                    try {
                        const devices = await navigator.mediaDevices.enumerateDevices();
                        const videoInputs = devices.filter(d => d.kind === 'videoinput');
                        if (videoInputs.some(d => d.label && d.label.length > 0)) {
                            this.cameraStatus = 'granted';
                        }
                    } catch (e) {}
                }
            }
        } else if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            this.cameraStatus = 'unsupported';
        }
        if (prev !== this.cameraStatus) {
            this.notify();
        }
        return this.cameraStatus;
    },

    async checkLocation() {
        const prev = this.locationStatus;
        if (navigator.permissions && navigator.permissions.query) {
            try {
                const res = await navigator.permissions.query({ name: 'geolocation' });
                this.locStatusObj = res;
                this.locationStatus = res.state;
                res.onchange = () => {
                    this.locationStatus = res.state;
                    this.notify();
                };
            } catch (err) {
                // query unsupported fallback
            }
        } else if (!navigator.geolocation) {
            this.locationStatus = 'unsupported';
        }
        if (prev !== this.locationStatus) {
            this.notify();
        }
        return this.locationStatus;
    },

    async checkAll() {
        await Promise.all([this.checkCamera(), this.checkLocation()]);
        this.notify();
        return {
            camera: this.cameraStatus,
            location: this.locationStatus
        };
    },

    // Trigger real browser native camera permission prompt
    async requestCamera() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            this.cameraStatus = 'unsupported';
            this.notify();
            return 'unsupported';
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            // Release temporary stream tracks immediately so it does not interfere with /video_feed
            stream.getTracks().forEach(track => track.stop());
            this.cameraStatus = 'granted';
            this.notify();
            return 'granted';
        } catch (err) {
            console.warn('Camera request ended:', err);
            let finalState = 'denied';
            if (navigator.permissions && navigator.permissions.query) {
                try {
                    const p = await navigator.permissions.query({ name: 'camera' });
                    finalState = p.state;
                } catch (e) {}
            }
            this.cameraStatus = finalState;
            this.notify();
            return finalState;
        }
    },

    // Trigger real browser native geolocation permission prompt
    requestLocation() {
        return new Promise((resolve) => {
            if (!navigator.geolocation) {
                this.locationStatus = 'unsupported';
                this.notify();
                return resolve('unsupported');
            }

            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    this.locationStatus = 'granted';
                    this.notify();
                    resolve('granted');
                },
                (err) => {
                    console.warn('Location request ended:', err);
                    const finalState = (err.code === err.PERMISSION_DENIED) ? 'denied' : 'prompt';
                    this.locationStatus = finalState;
                    this.notify();
                    resolve(finalState);
                },
                { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
            );
        });
    },

    init() {
        this.checkAll();

        // Refresh on window focus and tab visibility change
        window.addEventListener('focus', () => {
            this.checkAll();
        });

        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                this.checkAll();
            }
        });
    }
};

// Initialize globally
if (typeof window !== 'undefined') {
    window.SafeDrivePermissions = SafeDrivePermissions;
    SafeDrivePermissions.init();
}
