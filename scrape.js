'use strict';

const fs = require('fs');
var gs = require('github-scraper');

var url = process.argv[2];
gs(url, function(err, data) {
	if (err) process.exit(1);

	let jsonData = JSON.stringify(data, null, 2);  
	var filename = url.split('/')[0] + '-' + url.split('/')[1];
	fs.writeFile('/scrapes/' + filename + '.json', jsonData, (err) => {  
	    if (err) process.exit(1);
	    console.log('Data written to file');
	});
});

