function CPAPIClient() {
	this._bearer = function () {
		return localStorage.getItem("ApiBearerToken");
	};

	this._clearBearer = function () {
		localStorage.removeItem("ApiBearerToken")
	}

	this._request = function (url, method, payload, callback, error) {
		var retries = 3;
		var self = this;
		payload = payload && typeof payload === "object" ? JSON.stringify(payload) : payload;

		function invokeWithFreshBearer(xhr) {
			var req = new XMLHttpRequest();
			req.open("GET", "/GetBearerToken");
			req.addEventListener("load", function () {
				var bearer = JSON.parse(this.responseText);
				localStorage.setItem("ApiBearerToken", bearer);
				xhr.setRequestHeader("Authorization", "Bearer " + bearer);
				xhr.send(payload);
			})
			req.send();
		}

		function makeRequest() {
			var xhr = new XMLHttpRequest()
			xhr.open(method, url);
			xhr.addEventListener("load", function () {
				if (this.status === 401 && retries > 0) {
					console.log("Token expired. Retrying...", retries);
					retries--;
					self._clearBearer();
					makeRequest();
					return;
				}
				if (this.status >= 400 || retries < 1) {
					(typeof error === 'function') && error({xhr: this, error: "Request Failed!"});
					return;
				}
				try {
					var obj = JSON.parse(this.responseText);
					callback(obj);
				} catch (e) {
					(typeof error === 'function') && error({xhr: this, error: e});
					console.error(e);
				}
			});
			(method === "POST") && xhr.setRequestHeader("Content-Type", "application/json; charset=utf-8");
			var bearer = self._bearer();
			if (!bearer) {
				invokeWithFreshBearer(xhr);
				return;
			}
			xhr.setRequestHeader("Authorization", "Bearer " + bearer);
			xhr.send(payload);
		}

		makeRequest();
	};

	this.get = function (url, callback, error) {
		return this._request(url, "GET", null, callback, error);
	};

	this.post = function (url, payload, callback, error) {
		return this._request(url, "POST", payload, callback, error);
	}
}
